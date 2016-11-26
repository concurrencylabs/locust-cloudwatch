from locust import HttpLocust, TaskSet, events


def index(l):
    l.client.get("/")

class UserBehavior(TaskSet):
    tasks = {index:1}

    def on_start(self):
        index(self)

class WebsiteUser(HttpLocust):
    task_set = UserBehavior
    min_wait=15000
    max_wait=30000


