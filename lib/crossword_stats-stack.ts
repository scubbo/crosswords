import * as cdk from '@aws-cdk/core';
import {StaticWebsiteWithApi} from "./static-website-with-api";
import {AttributeType, Table} from "@aws-cdk/aws-dynamodb";
import {PolicyStatement} from "@aws-cdk/aws-iam";

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
      pathToAssetCode: 'lambda/',
      apiDomainRecord: 'api.crossword'
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
    })

  }
}
