import boto3
import json
import os
from uuid import uuid4 as uuid


def handler(event, context):
    path = event["path"]
    first_path_segment = path.split('/')[1]
    if first_path_segment in methods:
        return methods[first_path_segment](event, context)

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain',
            'X-Clacks-Overhead': 'GNU Terry Pratchett'
        },
        'body': f'Hello! You have hit the path {event["path"]}!'
    }


def submit_score(event, context):
    cloudformation = boto3.resource('cloudformation')
    # TODO - are the docs at https://bit.ly/36TOxv4 wrong? They claim `.filter` has Return Type
    # `list(cloudformation.Stack)`, but trying to do `.filter(...)[0]` gives
    # `TypeError: 'cloudformation.stacksCollection' object is not subscriptable`
    #
    # GitHub issue here, I think: https://github.com/boto/boto3/issues/1903
    stack = next(iter(cloudformation.stacks.filter(StackName='CrosswordStatsStack')))
    table_name = [output['OutputValue']
                  for output in stack.outputs
                  if output.get('ExportName', '') == 'scoreTableName'][0]

    data = json.loads(event['body'])
    score_table = boto3.resource('dynamodb').Table(table_name)
    # TODO - check for duplicates
    with score_table.batch_writer() as batch:
        for score in data['scores']:
            batch.put_item(Item={
                'id': str(uuid()),
                'date': data['date'],
                'name': score['name'],
                'time': score['time']
            })

    return {
        'statusCode': 200,
        # TODO - apply these headers with common logic
        'headers': {
            'Content-Type': 'text/plain',
            'X-Clacks-Overhead': 'GNU Terry Pratchett'
        },
        'body': f'You hit the submit_score method. Received {len(data["scores"])} scores.'
    }

# I could probably do this by mapping explicit mappings/integrations in CDK to separate Functions.
# However, https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
# seems to suggest that this is a common pattern?
methods = {
    'submit_score': submit_score
}