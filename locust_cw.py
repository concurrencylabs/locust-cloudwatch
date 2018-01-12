# encoding: utf-8

import time, datetime, logging, boto3, os, sys, json
from locust import HttpLocust, TaskSet, task, events, web, main
from Queue import Queue

logging.basicConfig(level=logging.INFO)


#_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/
#CONFIG VALUES - feel free to update
CW_METRICS_NAMESPACE="concurrencylabs/loadtests/locust"
CW_LOGS_LOG_GROUP="LocustTests"
CW_LOGS_LOG_STREAM="load-generator"
#_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/_/


STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"


class RequestResult(object):
    def __init__(self, host, request_type, name, response_time, response_length, exception, status):
        self.timestamp = datetime.datetime.utcnow()
        self.request_type = request_type
        self.name = name
        self.response_time = response_time
        self.response_length = response_length
        self.host = host
        self.exception = exception
        self.status = status


    def get_cw_logs_record(self):
        record = {}
        timestamp = datetime.datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S.%f UTC")#example: 2016/02/08 16:51:05.123456 CST
        message = ""
        if self.status == STATUS_SUCCESS:
            message = '[timestamp={}] [host={}] [request_type={}] [name={}] [response_time={}] [response_length={}]'.format(timestamp, self.host, self.request_type, self.name, self.response_time, self.response_length)
        if self.status == STATUS_FAILURE:
            message = '[timestamp={}] [host={}] [request_type={}] [name={}] [response_time={}] [exception={}]'.format(timestamp, self.host, self.request_type, self.name, self.response_time, self.exception)
        record = {'timestamp': self.get_seconds()*1000,'message': message}
        return record

    def get_cw_metrics_status_record(self):
        dimensions = self.get_metric_dimensions()
        result = {}

        if self.status == STATUS_SUCCESS:
            result = {
                    'MetricName': 'ResponseTime_ms',
                    'Dimensions': dimensions,
                    'Timestamp': self.timestamp,
                    'Value': self.response_time,
                    'Unit': 'Milliseconds'

                  }
        if self.status == STATUS_FAILURE:
            result = {
                    'MetricName': 'FailureCount',
                    'Dimensions': dimensions,
                    'Timestamp': self.timestamp,
                    'Value': 1,
                    'Unit': 'Count'

                  }

        return result


    def get_cw_metrics_response_size_record(self):
        dimensions = self.get_metric_dimensions()

        result = {}

        if self.status == STATUS_SUCCESS:
            result = {
                    'MetricName': 'ResponseSize_Bytes',
                    'Dimensions': dimensions,
                    'Timestamp': self.timestamp,
                    'Value': self.response_length,
                    'Unit': 'Bytes'

                  }

        return result



    def get_cw_metrics_count_record(self):
        dimensions = self.get_metric_dimensions()
        result = {
                'MetricName': 'RequestCount',
                'Dimensions': dimensions,
                'Timestamp': self.timestamp,
                'Value': 1,
                'Unit': 'Count'
                  }
        return result



    def get_metric_dimensions(self):
        result =  [{'Name': 'Request','Value': self.name},{'Name': 'Host','Value': self.host}]
        return result


    #returns seconds since epoch
    def get_seconds(self):
        epoch = datetime.datetime.utcfromtimestamp(0)
        return int((self.timestamp - epoch).total_seconds())


class UserCount(object):
    def __init__(self, host,  usercount):
        self.host = host
        self.usercount = usercount

    def get_metric_data(self):
        result = []
        dimensions = [{'Name': 'Host','Value': self.host}]
        result = {
                'MetricName': 'UserCount','Dimensions': dimensions,'Timestamp': datetime.datetime.utcnow(),
                'Value': self.usercount, 'Unit': 'Count'
            }

        return result

"""
Utility class to keep track of time elapsed between events
"""

class Timestamp():

    def __init__(self):
        self.eventdict = {}

    def start(self,event):
        self.eventdict[event] = {}
        self.eventdict[event]['start'] = datetime.datetime.now()
        self.eventdict[event]['elapsed'] = 0

    def evaluate(self, event):
        delta = self.eventdict[event]['start'] - datetime.datetime.now()



    def finish(self, event):
        elapsed = datetime.datetime.now() - self.eventdict[event]['start']
        self.eventdict[event]['elapsed'] = elapsed
        return elapsed

    def elapsed(self,event):
        return self.eventdict[event]['elapsed']



class CloudWatchConnector(object):

    def __init__(self, host, namespace, loggroup, logstream, iamrolearn):
        seq = datetime.datetime.now().microsecond
        self.loggroup = loggroup
        self.logstream = logstream + "_" + str(seq)
        self.namespace = namespace #the same namespace is used for both CW Logs and Metrics
        self.nexttoken = ""
        self.response_queue = Queue()
        self.batch_size = 5
        self.host = host
        self.usercount = None
        self.iamrolearn = iamrolearn
        self.lastclientrefresh = None

        self.init_clients()



        if not self.loggroup_exists():
            self.cwlogsclient.create_log_group(logGroupName=self.loggroup)

        self.cwlogsclient.create_log_stream(logGroupName=self.loggroup,logStreamName=self.logstream)


    #TODO: if using roleArn, find a way to refresh the clients every 59 minutes (before the max duration of temp credentials expires)
    def init_clients(self):
        if self.iamrolearn:
            logging.info("Initializing AWS SDK clients using IAM Role:[{}]".format(self.iamrolearn))
            stsclient = boto3.client('sts')
            stsresponse = stsclient.assume_role(RoleArn=self.iamrolearn, RoleSessionName='cwlocustconnector')
            if 'Credentials' in stsresponse:
                accessKeyId = stsresponse['Credentials']['AccessKeyId']
                secretAccessKey = stsresponse['Credentials']['SecretAccessKey']
                sessionToken = stsresponse['Credentials']['SessionToken']
                self.cwlogsclient = boto3.client('logs',aws_access_key_id=accessKeyId, aws_secret_access_key=secretAccessKey,aws_session_token=sessionToken)
                self.cwclient = boto3.client('cloudwatch',aws_access_key_id=accessKeyId, aws_secret_access_key=secretAccessKey,aws_session_token=sessionToken)

        else:
            self.cwlogsclient = boto3.client('logs')
            self.cwclient = boto3.client('cloudwatch')

        self.lastclientrefresh = datetime.datetime.now()


    #See the list of Locust events here: http://docs.locust.io/en/latest/api.html#events

    def on_locust_start_hatching(self, **kwargs):
        """
        Event handler that get triggered when start hatching
        """
        logging.info("Started hatching [{}]".format(kwargs))

    def on_request_success(self, request_type, name, response_time, response_length, **kwargs):
        request_result = RequestResult(self.host, request_type, name, response_time, response_length, "", STATUS_SUCCESS)
        self.response_queue.put(request_result)


    def on_request_failure(self, request_type, name, response_time, exception, **kwargs):
        request_result = RequestResult(self.host, request_type, name, response_time, 0, exception, STATUS_FAILURE)
        self.response_queue.put(request_result)

    def on_request_error(locust_instance, exception, tb, **kwargs):
        """
        Event handler that get triggered on every Locust error
        """

    def on_hatch_complete(self, user_count):
        #TODO:Register event in CloudWatch Logs
        self.usercount = UserCount(host=self.host, usercount=user_count)
        self.start_cw_loop()


    def on_quitting(user_count):
        """
        Event handler that get triggered when when the locust process is exiting
        """

    def on_report_to_master(client_id, data):
        """
        This event is triggered on the slave instances every time a stats report is
        to be sent to the locust master. It will allow us to add our extra content-length
        data to the dict that is being sent, and then we clear the local stats in the slave.
        """

    def on_slave_report(client_id, data):
        """
        This event is triggered on the master instance when a new stats report arrives
        from a slave. Here we just add the content-length to the master's aggregated
        stats dict.
        """

    def loggroup_exists(self):
        result = False
        response = self.cwlogsclient.describe_log_groups(logGroupNamePrefix=self.loggroup, limit=1)
        if len(response['logGroups']): result = True
        return result



    def start_cw_loop(self):
        while True:
            awsclientage = datetime.datetime.now() - self.lastclientrefresh
            #Refresh AWS clients every 50 minutes, if using an IAM Role (since credentials expire in 1hr)
            if self.iamrolearn and awsclientage.total_seconds() > 50*60 :
                self.init_clients()

            time.sleep(.1)
            batch = self.get_batch()
            cw_logs_batch = batch['cw_logs_batch']
            cw_metrics_batch = batch['cw_metrics_batch']
            if cw_logs_batch:
                try:
                    if self.nexttoken:
                        response = self.cwlogsclient.put_log_events(
                            logGroupName=self.loggroup, logStreamName=self.logstream,
                            logEvents=cw_logs_batch,
                            sequenceToken=self.nexttoken
                        )
                    else:
                        response = self.cwlogsclient.put_log_events(
                            logGroupName=self.loggroup, logStreamName=self.logstream,
                            logEvents=cw_logs_batch
                        )
                    if 'nextSequenceToken' in response: self.nexttoken = response['nextSequenceToken']
                except Exception as e:
                    logging.error(str(e))

            if cw_metrics_batch:
                try:
                    cwresponse = self.cwclient.put_metric_data(Namespace=self.namespace,MetricData=cw_metrics_batch)
                    logging.debug("PutMetricData response: [{}]".format(json.dumps(cwresponse, indent=4)))
                except Exception as e:
                    logging.error(str(e))


    """
    Metric and Log data has to be batched before writing to the CloudWatch API.
    """
    def get_batch(self):
        result = {}
        cw_logs_batch = []
        cw_metrics_batch = []
        if self.response_queue.qsize() >= self.batch_size:
            for i in range(0, self.batch_size):
                request_response = self.response_queue.get()
                cw_logs_batch.append(request_response.get_cw_logs_record())
                cw_metrics_batch.append(request_response.get_cw_metrics_status_record())
                cw_metrics_batch.append(request_response.get_cw_metrics_count_record())
                if request_response.get_cw_metrics_response_size_record():
                    cw_metrics_batch.append(request_response.get_cw_metrics_response_size_record())
                if self.usercount: cw_metrics_batch.append(self.usercount.get_metric_data())

                self.response_queue.task_done()
            logging.debug("Queue size:["+str(self.response_queue.qsize())+"]")
        result['cw_logs_batch']=cw_logs_batch
        result['cw_metrics_batch']=cw_metrics_batch
        return result


if __name__ == "__main__":

   parser, options, arguments = main.parse_options()

   host = ''
   if options.host:
       host = options.host

   #this parameter is supported in case the load generator publishes metrics to CloudWatch in a different AWS account
   iamrolearn = ''
   if 'IAM_ROLE_ARN' in os.environ:
       iamrolearn = os.environ['IAM_ROLE_ARN']


   cwconn = CloudWatchConnector(host=host, namespace=CW_METRICS_NAMESPACE,loggroup=CW_LOGS_LOG_GROUP,logstream=CW_LOGS_LOG_STREAM, iamrolearn=iamrolearn)

   events.locust_start_hatching += cwconn.on_locust_start_hatching
   events.request_success += cwconn.on_request_success
   events.request_failure += cwconn.on_request_failure
   events.hatch_complete += cwconn.on_hatch_complete

   main.main()
