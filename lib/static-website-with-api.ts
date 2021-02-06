import * as cdk from '@aws-cdk/core';
import { Bucket } from '@aws-cdk/aws-s3';
import {BucketDeployment, Source} from "@aws-cdk/aws-s3-deployment";
import {ARecord, CnameRecord, HostedZone, IHostedZone, RecordTarget} from "@aws-cdk/aws-route53";
import { strict as assert } from 'assert';
import {AssetCode, Function, Runtime} from "@aws-cdk/aws-lambda";
import {LambdaRestApi} from "@aws-cdk/aws-apigateway";
import {ApiGateway} from "@aws-cdk/aws-route53-targets";
import {Certificate} from "@aws-cdk/aws-certificatemanager";

export interface StaticWebsiteWithApiProps {
    websiteDomainRecord?: string,
    staticBucket?: Bucket,
    websiteIndexDocument?: string,
    pathToStaticSiteSources: string,
    rootDomain: string,
    apiLambda?: Function, // Exactly one of this and pathToAssetCode must be set
    pathToAssetCode?: string, // Exactly one of this and apiLambda must be set
    functionHandler?: string,
    apiDomainRecord?: string,
    [key: string]: any // This is necessary in order to do `props[propertyName]` -
}

export class StaticWebsiteWithApi extends cdk.Construct {
    constructor(scope: cdk.Construct, id: string, props: StaticWebsiteWithApiProps) {
        super(scope, id);

        this.assertExactlyOnePropertySet(props, ['function', 'pathToAssetCode']);

        const zone = HostedZone.fromLookup(this, 'baseZone', {
            domainName: props.rootDomain
        })
        this.createStaticSiteResources(zone, props);
        this.createLogicalResources(zone, props);
    }

    private createLogicalResources(zone: IHostedZone, props: StaticWebsiteWithApiProps) {
        let apiFunc;
        if (props.apiLambda != undefined) {
            apiFunc = props.apiLambda;
        } else {
            apiFunc = new Function(this, 'backend-lambda', {
                // pathToAssetCode is guaranteed defined by asssertExactlyOnePropertySet,
                // but TypeScript doesn't know that
                // (I could probably do this more idiomatically with a Type Guard,
                // but I'm still learning TypeScript!)
                code: new AssetCode(props.pathToAssetCode as string),
                handler: props.functionHandler ?? 'index.handler',
                runtime: Runtime.PYTHON_3_8
            })
        }
        const api = new LambdaRestApi(this, 'api', {
            handler: apiFunc,
            proxy: true,
            deploy: true,
            domainName: {
                domainName: (props.apiDomainRecord != undefined ? props.apiDomainRecord : 'api') + '.' + props.rootDomain,
                certificate: new Certificate(this, 'api-certificate', {
                    domainName: (props.apiDomainRecord != undefined ? props.apiDomainRecord : 'api') + '.' + props.rootDomain
                })
            }
        })
        new ARecord(this, 'apiDNS', {
            zone: zone,
            recordName:
                props.apiDomainRecord != undefined ?
                    props.apiDomainRecord :
                    'api',
            target: RecordTarget.fromAlias(new ApiGateway(api))
        })
    }

    private createStaticSiteResources(zone: IHostedZone, props: StaticWebsiteWithApiProps) {
        // Static site resources
        let staticSiteBucket;
        if (props.staticBucket == undefined) {
            staticSiteBucket = new Bucket(this, 'static-website-bucket', {
                bucketName: ((props.websiteDomainRecord != undefined) ? props.websiteDomainRecord + '.' : '') + props.rootDomain,
                publicReadAccess: true,
                removalPolicy: cdk.RemovalPolicy.DESTROY,
                websiteIndexDocument: props.websiteIndexDocument?? 'index.html'
            })
        } else {
            staticSiteBucket = props.staticBucket;
        }

        new BucketDeployment(this, 'deploy-static-website', {
            sources: [Source.asset(props.pathToStaticSiteSources)],
            destinationBucket: staticSiteBucket
        })
        new CnameRecord(this, 'cnameForWebsite', {
            zone: zone,
            recordName: props.websiteDomainRecord,
            domainName: staticSiteBucket.bucketWebsiteDomainName
        })
    }

    private assertExactlyOnePropertySet(props: StaticWebsiteWithApiProps, property_names: string[]) {
        assert(
            property_names
                .map((propertyName) => (props[propertyName] == undefined) ? 1 : 0)
                .reduce((a, b) => a+b, 0 as number) == 1,
            `Exactly one of the properties ${property_names} must be present`);
    }

}