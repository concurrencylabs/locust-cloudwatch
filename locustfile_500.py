import random
from locust import HttpLocust, TaskSet, events

"""
This locustfile is intended for testing a WordPress site that is preloaded with
500 posts. It randomly generates a URL between 1 and 500, so it generates load
evenly across all posts in the test WordPress site.
"""

def index(l):
    l.client.get("/?p="+str(random.randrange(1,500,1)),name="/?p=[postId]")


class UserBehavior(TaskSet):
    tasks = {index:1}


    def on_start(self):
        index(self)


class WebsiteUser(HttpLocust):
    task_set = UserBehavior
    min_wait=15000
    max_wait=30000
