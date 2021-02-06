import * as cdk from '@aws-cdk/core';
import {StaticWebsiteWithApi} from "./static-website-with-api";

export class CrosswordStatsStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, {
      ...props,
      // https://github.com/aws-samples/aws-cdk-examples/issues/238
      // TODO - figure out a better way of doing this (probably, via CI/CD)
      env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: process.env.CDK_DEFAULT_REGION
      }});

    new StaticWebsiteWithApi(this, 'static-website-with-api', {
      websiteDomainRecord: 'crossword',
      pathToStaticSiteSources: 'static-site/',
      rootDomain: 'scubbo.org',
      pathToAssetCode: 'lambda/',
      apiDomainRecord: 'api.crossword'
    });

  }
}
