import * as cdk from '@aws-cdk/core';
import {CfnParameter, CustomResource, Duration} from '@aws-cdk/core';
import {StaticWebsiteWithApi} from "./static-website-with-api";
import {AttributeType, Table} from "@aws-cdk/aws-dynamodb";
import {Effect, PolicyStatement} from "@aws-cdk/aws-iam";
import {Secret} from "@aws-cdk/aws-secretsmanager";
import {Rule, RuleTargetInput, Schedule} from "@aws-cdk/aws-events";
import {LambdaFunction} from "@aws-cdk/aws-events-targets";
import {PythonFunction} from "@aws-cdk/aws-lambda-python";
import {RetentionDays} from "@aws-cdk/aws-logs";

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

    const emailNotificationParameter = new CfnParameter(this, 'NotifyOnFailureParameter');
    const emailNotificationBoolean = emailNotificationParameter.valueAsString.toLowerCase() === 'true'

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
            path: '/update_scores',
            emailNotification: emailNotificationBoolean
          })
        })
      ]
    });

    if (emailNotificationBoolean) {
      const emailNotificationTable = new Table(this, 'NotifyOnFailureTable', {
        partitionKey: { name: 'date', type: AttributeType.STRING }
      })
      emailNotificationTable.grantReadWriteData(websiteAndApi.apiFunction)
      new cdk.CfnOutput(this, 'email-table-name-output', {
        exportName: 'emailTableName',
        value: emailNotificationTable.tableName
      });

      // https://medium.com/poka-techblog/verify-domains-for-ses-using-cloudformation-8dd185c9b05c
      const emailVerificationLambda = new PythonFunction(this, 'EmailVerificationLambda', {
        entry: 'lambda/ses_domain_verification/',
        logRetention: RetentionDays.ONE_WEEK,
        timeout: Duration.minutes(1)
      });
      new CustomResource(this, 'EmailVerificationResource', {
        resourceType: 'Custom::AmazonSesVerificationRecords',
        serviceToken: emailVerificationLambda.functionArn,
        properties: {
          hostedZoneId: websiteAndApi.hostedZone.hostedZoneId
        }
      });
      emailVerificationLambda.role?.addToPolicy(new PolicyStatement({
        actions: [
            'route53:GetHostedZone',
            'route53:ChangeResourceRecordSets'
        ],
        effect: Effect.ALLOW,
        resources: [websiteAndApi.hostedZone.hostedZoneArn]
      }));
      emailVerificationLambda.role?.addToPolicy(new PolicyStatement({
        actions: [
          'ses:VerifyDomainDkim',
          'ses:VerifyDomainIdentity'
        ],
        effect: Effect.ALLOW,
        resources: ['*']
      }));
    }

  }
}
