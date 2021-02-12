import boto3
import json
import os
from datetime import datetime, timedelta
from uuid import uuid4 as uuid

FOUR_DAYS = timedelta(days=4)
DATE_FORMAT = '%Y-%m-%d'


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
    score_table = _get_score_table()
    data = json.loads(event['body'])

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

def get_data(event, context):
    score_table = _get_score_table()
    # TODO - don't hard-code the date
    current_date = datetime.now()
    data = score_table.scan(
        ExpressionAttributeNames={
            '#d': 'date'
        },
        ExpressionAttributeValues={
            ':val1': f'{(current_date-FOUR_DAYS).strftime(DATE_FORMAT)}',
            ':val2': f'{current_date.strftime(DATE_FORMAT)}'
        },
        FilterExpression='#d between :val1 and :val2',
    )

    return {
      'statusCode': 200,
      'headers': {
            'Content-Type': 'application/json',
            'X-Clacks-Overhead': 'GNU Terry Pratchett',
            'Access-Control-Allow-Origin': '*' # TODO - not this.
      },
      'body': json.dumps(_reformat_score_data(data))
    }

def _reformat_score_data(data_from_dynamo):
    # This could _probably_ be done in a single pass,
    # but what the heck, this isn't exactly a performance-intensive
    # high-TPS Lambda, nor is it a whiteboarding interview :P
    #
    # (Plus, from what I can see, DynamoDB scans cannot return items
    # in sorted order, which would probably be a prerequisite to do this
    # in some pleasingly-Big-O way)
    dates = []
    intermediate_score_lookup = {}
    for item in data_from_dynamo['Items']:
        if item['name'] not in intermediate_score_lookup:
            intermediate_score_lookup[item['name']] = {}
        if item['date'] not in dates:
            dates.append(item['date'])
        intermediate_score_lookup[item['name']][item['date']] = int(item['time'])

    dates.sort()
    return_data = {'dates':dates, 'scores':{}}
    # For each person, construct an array of scores, in order matching the dates
    # (with `None` representing missing scores)
    for name in intermediate_score_lookup:
        personal_scores = []
        for date in dates:
            if date in intermediate_score_lookup[name]:
                personal_scores.append(intermediate_score_lookup[name][date])
            else:
                personal_scores.append(None)
        return_data['scores'][name] = personal_scores

    return return_data

def _get_score_table():
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

    return boto3.resource('dynamodb').Table(table_name)

# I could probably do this by mapping explicit mappings/integrations in CDK to separate Functions.
# However, https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
# seems to suggest that this is a common pattern?
#
# TODO: I bet there's a way to auto-generate this mapping with annotations.
methods = {
    'submit_score': submit_score,
    'get_data': get_data
}
