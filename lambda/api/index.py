import boto3
import hashlib
import requests

from datetime import datetime, time, timedelta, timezone

from bs4 import BeautifulSoup
from typing import Iterable
from urllib import parse

import logging
# https://stackoverflow.com/questions/37703609
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


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
    if not params:
        params = {}

    # Expected format: `2021-02-08_2021-02-11`
    date_range_string = params.get('date_range', '_')
    # Using `_` as the fallback because that is also what jQuery explicitly sends when no dates
    # are selected.
    # TODO - better default-case handling!
    if date_range_string == '_':
        date_range_string = f'{(datetime.now()-FOUR_DAYS).strftime(DATE_FORMAT)}_{datetime.now().strftime(DATE_FORMAT)}'
    date_range = date_range_string.split('_')

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

    statistic = params.get('statistic', 'standard')

    return _reformat_score_data(statistic, data)


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

    now = datetime.now(timezone.utc)
    shouldEmailNotification = event.get('emailNotification', '').lower() is 'true'

    try:
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
        # TODO - check scores for own username, and send reminder if not received by given time
        return True
    except Exception as e:
        LOG.exception(e)
        # TODO - customizable time threshold
        # TODO - consider boundary issues
        date_string = now.strftime(DATE_FORMAT)
        if now.time() > time(17, 0, 0, 0, timezone.utc) and \
                shouldEmailNotification and \
                not _have_reported_failure_for_date(date_string):
            # TODO - actually send email
            LOG.info(f'Reported failure: {e}')
            _record_reported_failure(date_string)


def _record_reported_failure(date_string: str):
    email_information = _get_email_information_for_date(date_string)
    if 'date' not in email_information:
        email_information['date'] = date_string
    email_information['haveReportedFailure'] = {'B': True}
    _get_email_table().put_item(Item=email_information)


def _have_reported_failure_for_date(date_string: str):
    email_information = _get_email_information_for_date(date_string)
    # Default to "True" in order to prevent spam reporting in case of meta-failure
    return email_information.get('haveReportedFailure', {}).get('B', True)


def _get_email_information_for_date(date_string: str):
    table = _get_email_table()
    return table.get_item(Key={'date': {'S': date_string}}).get('Item', {})


def _get_email_notification_date_info():
    return boto3.client('dynamo')


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


def _reformat_score_data(statistic, data_from_dynamo):
    if statistic == 'standard':
        return _reformat_score_data_standard(data_from_dynamo)
    if statistic == 'deviation_from_average':
        return _reformat_score_data_deviation(data_from_dynamo)


def _reformat_score_data_standard(data_from_dynamo):
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


def _reformat_score_data_deviation(data_from_dynamo):
    # See above for my defence against the hideous inefficiency of this :P
    running_averages = {}
    intermediate_score_lookup = {}
    for item in data_from_dynamo['Items']:
        if item['name'] not in intermediate_score_lookup:
            intermediate_score_lookup[item['name']] = {}
        if item['date'] not in running_averages:
            running_averages[item['date']] = []
        time = int(item['time'])
        intermediate_score_lookup[item['name']][item['date']] = time
        running_averages[item['date']].append(time)

    dates = list(running_averages.keys()).copy()
    dates.sort()

    def average(iterable: Iterable[int]):
        sum = 0
        count = 0
        for i in iterable:
            sum += i
            count += 1
        return sum // count

    averages = {k: average(v) for k, v in running_averages.items()}
    return_data = {'dates': dates, 'scores': {}}

    for name in intermediate_score_lookup:
        personal_scores = []
        for date in dates:
            average_for_date = averages[date]
            if date in intermediate_score_lookup[name]:
                # Note - this is _not_ the proper mathematical definition of "variance".
                personal_scores.append(
                    (intermediate_score_lookup[name][date] - average_for_date) / average_for_date)
            else:
                personal_scores.append(None)
        return_data['scores'][name] = personal_scores

    return return_data


def _get_email_table():
    return _get_table_by_export_name('emailTableName')


def _get_score_table():
    return _get_table_by_export_name('scoreTableName')


def _get_table_by_export_name(export_name: str):
    cloudformation = boto3.resource('cloudformation')
    # TODO - are the docs at https://bit.ly/36TOxv4 wrong? They claim `.filter` has Return Type
    # `list(cloudformation.Stack)`, but trying to do `.filter(...)[0]` gives
    # `TypeError: 'cloudformation.stacksCollection' object is not subscriptable`
    #
    # GitHub issue here, I think: https://github.com/boto/boto3/issues/1903
    stack = next(iter(cloudformation.stacks.filter(StackName='CrosswordStatsStack')))
    table_name = [output['OutputValue']
                  for output in stack.outputs
                  if output.get('ExportName', export_name) == ''][0]

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
