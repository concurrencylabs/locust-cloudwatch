
## Locust/CloudWatch Connector

This repo contains code and a CloudFormation template to publish <a href="http://locust.io/" target="new">Locust</a> test result metrics
to AWS CloudWatch.

It will allow you to see something like this in a CloudWatch dashboard:

![Locust CW metrics](https://www.concurrencylabs.com/img/posts/14-locust-cw-connector/locust-metrics-20.png")

Which is very useful, since you can have load test results metrics in the same place as AWS system metrics
(i.e. EC2 CPUUtilization, NetworkIn, etc.), which will make it much easier to analyze load test results.

For more details, <a href="https://www.concurrencylabs.com/blog/how-to-export-locust-metrics-to-cloudwatch/" target="new">read this article</a>.


### The CloudFormation template

The CloudFormation template ```locust-cloudwatch.yml``` launches an EC2 instance loaded with
Locust and with the custom Python module ```locust_cw.py```, as well as a sample Locust test module.
It also creates an EC2 Instance Profile with the permissions required to create log groups,
log streams and publish metrics to CloudWatch.

A t2.nano is usually enough to generate some decent load, but you can always modify the template
to use a different instance type.


<a href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=LocustCloudwatchConnector&templateURL=http://s3.amazonaws.com/concurrencylabs-cfn-templates/locust-cloudwatch/locust-cloudwatch.yml" target="new"><img src="https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png" alt="Launch Stack"></a> 



### Launching a test

Login to the EC2 instance launched in the CloudFormation template. You can see its public IP
either in the EC2 console, or in the Outputs tab in the CloudFormation console.

ssh -i <location of your EC2 keys> ec2-user@<public IP of Locust instance>

Go to the ```~/locust``` folder.

I left the AWS region out of the code, on purpose. Therefore you have to first set the AWS region as an environment variable:

```export AWS_DEFAULT_REGION=<us-east-1|us-west-2|etc.>```


Typically, you would launch Locust tests with the following command:

```
locust --host=http://<URL to test> -f <yourlocustfile.py>
```

Instead, we'll launch Locust in the following way:

```
python locust_cw.py --host=http://<URL to test> -f <yourlocustfile.py>
```

You'll be able to use all supported Locust command line options.


### The locust_cw.py module

The ```locust_cw.py``` module implements Locust event hooks and some utility methods that call AWS
CloudWatch APIs in response to Locust event hooks. For example, each time a response result is received,
the module sends the result to an internal queue, which is later used to publish to CloudWatch and CloudWatch Logs.

I implemented it this way, so it wouldn't be necessary to update a single locustfile (Python module
that contains your test definition). This reduces friction to a minimum. So, if you already have
locustfiles, you don't have to change them at all!

In this version, the following values are hard-coded: CW_METRICS_NAMESPACE, CW_LOGS_LOG_GROUP and CW_LOGS_LOG_STREAM.
Feel free to update them as you see fit.

I also implemented this module so I wouldn't have to update any core locust components.

The ```locust_cw.py``` module  calls CloudWatch APIs. The CloudWatch template creates an IAM
Role and EC2 Instance Profile for this purpose, so you don't have to configure permissions
manually or store AWS keys in the Locust EC2 instance.


### Security Groups

The CloudFormation template creates a Security Group that is open for port 8089 (the port
used by the Locust web interface). I strongly recommend you restrict access to this port
based on your workstation's IP, or your VPN.







