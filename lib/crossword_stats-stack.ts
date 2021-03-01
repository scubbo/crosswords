import * as cdk from '@aws-cdk/core';
import {StaticWebsiteWithApi} from "./static-website-with-api";
import {AttributeType, Table} from "@aws-cdk/aws-dynamodb";
import {PolicyStatement} from "@aws-cdk/aws-iam";
import {Secret} from "@aws-cdk/aws-secretsmanager";
import {Rule, RuleTargetInput, Schedule} from "@aws-cdk/aws-events";
import {LambdaFunction} from "@aws-cdk/aws-events-targets";

export class CrosswordStatsStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, {
      ...props,
      // https://github.com/aws-samples/aws-cdk-examples/issues/238
      // TODO - figure out a better way of doing this (probably, via CI/CD)
      env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: process.env.CDK_DEFAULT_REGION
      },
    stackName: 'CrosswordStatsStack'});

    const websiteAndApi = new StaticWebsiteWithApi(this, 'static-website-with-api', {
      websiteDomainRecord: 'crossword',
      pathToStaticSiteSources: 'static-site/',
      rootDomain: 'scubbo.org', // Replace this with your own domain!
      pathToAssetCode: 'lambda/api/',
    });
    websiteAndApi.apiFunction.addToRolePolicy(new PolicyStatement({
      actions: ['cloudformation:DescribeStacks'],
      resources: ['*'],
    }))

    const scoreTable = new Table(this, 'Table', {
      partitionKey: { name: 'id', type: AttributeType.STRING },
      sortKey: { name: 'date', type: AttributeType.STRING },
    });
    scoreTable.grantReadWriteData(websiteAndApi.apiFunction)
    new cdk.CfnOutput(this, 'score-table-name-output', {
      exportName: 'scoreTableName',
      value: scoreTable.tableName
    });

    const nytCookie = new Secret(this, 'Cookie-Secret', {
      secretName: 'nyt-cookie'
    });
    nytCookie.grantRead(websiteAndApi.apiFunction);
    nytCookie.grantWrite(websiteAndApi.apiFunction);

    new Rule(this, 'HeartbeatRule', {
      enabled: true,
      schedule: Schedule.expression('rate(5 minutes)'),
      targets: [
        new LambdaFunction(websiteAndApi.apiFunction, {
          event: RuleTargetInput.fromObject({
            path: '/update_scores'
          })
        })
      ]
    });

  }
}
