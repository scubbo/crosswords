import boto3
import hashlib
import requests

from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from urllib import parse


FOUR_DAYS = timedelta(days=4)
DATE_FORMAT = '%Y-%m-%d'

SECRET_ID = 'nyt-cookie'


def handler(event, context):
    path = event["path"]
    first_path_segment = path.split('/')[1]
    if first_path_segment in methods:
        return methods[first_path_segment](event, context)

    return f'Hello! You have hit the path {event["path"]}!'


def get_data(event, context):
    params = event.get('queryStringParameters')
    # Can't do `event.get('queryStringParameters', {})` because it's always
    # present (`None` if no params)
    if params:
        date_range = params.get('date_range', None)
    else:
        date_range = None
    if date_range:
        # Expected format: `2021-02-08_2021-02-11`
        date_range = date_range.split('_')
    else:
        now = datetime.now()
        date_range = ((now-FOUR_DAYS).strftime(DATE_FORMAT), now.strftime(DATE_FORMAT))

    score_table = _get_score_table()
    data = score_table.scan(
        ExpressionAttributeNames={
            '#d': 'date'
        },
        ExpressionAttributeValues={
            ':val1': date_range[0],
            ':val2': date_range[1]
        },
        FilterExpression='#d between :val1 and :val2',
    )

    return _reformat_score_data(data)


def update_cookie(event, context):
    cookie_text = event['body']
    secrets = boto3.client('secretsmanager')
    current_secret = secrets.get_secret_value(
        SecretId=SECRET_ID
    ).get('SecretString', '')
    if current_secret == cookie_text:
        # No change - do nothing
        return False

    secrets.put_secret_value(
        SecretId=SECRET_ID,
        SecretString=cookie_text
    )
    return True


def update_scores(event, context):
    secrets = boto3.client('secretsmanager')
    cookies_secret = secrets.get_secret_value(
        SecretId=SECRET_ID).get('SecretString', '')
    cookies = dict([(i.split('=')[0], parse.unquote(i.split('=')[1]))
                    for i in cookies_secret.split('; ')])
    r = requests.get('https://www.nytimes.com/puzzles/leaderboards', cookies=cookies)
    soup = BeautifulSoup(r.text, features="html.parser")
    score_divs = [div for div in
                  soup.find_all('div', {'class': 'lbd-score'})
                  if 'no-rank' not in div['class']]
    scores = [{
        'name': _get_name(div),
        'time': _get_time(div)
    } for div in score_divs]
    date = _get_date(soup)

    score_table = _get_score_table()

    with score_table.batch_writer() as batch:
        for score in scores:
            batch.put_item(Item={
                'id': _build_id(date, score),
                'date': date,
                'name': score['name'],
                'time': score['time']
            })
            print(f'DEBUG - putting data to Dynamo: {date}:{score}')
    return True


def _build_id(date, score):
    return hashlib.md5(f'{date}_{score["name"]}'.encode('utf-8')).hexdigest()


def _get_name(div):
    return div.find_all('p', {'class': 'lbd-score__name'})[0].text.replace('(you)', '').strip()


def _get_time(div):
    split = div.find_all('p', {'class': 'lbd-score__time'})[0].text.split(':')
    return 60*int(split[0]) + int(split[1])


def _get_date(soup):
    date_string = soup.find_all('h3', {'class': 'lbd-type__date'})[0].text
    split = date_string.split(' ')
    year = split[3]
    # +1 because the Gregorian Calendar's months are not 0-indexed
    month = str(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'].index(split[1])+1).rjust(2, '0')
    day = str(split[2][0: -1]).rjust(2, '0')
    return '-'.join([year, month, day])


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
    'update_cookie': update_cookie,
    'update_scores': update_scores,
    'get_data': get_data
}