import * as cdk from '@aws-cdk/core';
import {Fn} from '@aws-cdk/core';
import {Bucket} from '@aws-cdk/aws-s3';
import {BucketDeployment, Source} from "@aws-cdk/aws-s3-deployment";
import {ARecord, HostedZone, IHostedZone, RecordTarget} from "@aws-cdk/aws-route53";
import {strict as assert} from 'assert';
import {AssetCode, Function, Runtime} from "@aws-cdk/aws-lambda";
import {PythonFunction} from "@aws-cdk/aws-lambda-python";
import {LambdaRestApi} from "@aws-cdk/aws-apigateway";
import {ApiGateway} from "@aws-cdk/aws-route53-targets";
import {Certificate, CertificateValidation} from "@aws-cdk/aws-certificatemanager";
import {RetentionDays} from "@aws-cdk/aws-logs";

export interface StaticWebsiteWithApiProps {
    websiteDomainRecord?: string,
    staticBucket?: Bucket,
    websiteIndexDocument?: string,
    pathToStaticSiteSources: string,
    rootDomain: string,
    apiLambda?: Function, // Exactly one of this and pathToAssetCode must be set
    pathToAssetCode?: string, // Exactly one of this and apiLambda must be set
    functionHandler?: string,
    [key: string]: any // This is necessary in order to do `props[propertyName]` -
}

export class StaticWebsiteWithApi extends cdk.Construct {
    apiFunction: Function;
    hostedZone: IHostedZone; // Externally accessed to permit SES-sending
    private staticSiteBucket: Bucket

    constructor(scope: cdk.Construct, id: string, props: StaticWebsiteWithApiProps) {
        super(scope, id);

        this.assertExactlyOnePropertySet(props, ['function', 'pathToAssetCode']);

        this.hostedZone = HostedZone.fromLookup(this, 'baseZone', {
            domainName: props.rootDomain
        })
        this.createStaticSiteResources(this.hostedZone, props);
        this.createLogicalResources(this.hostedZone, props);
    }

    private createLogicalResources(zone: IHostedZone, props: StaticWebsiteWithApiProps) {
        if (props.apiLambda != undefined) {
            this.apiFunction = props.apiLambda;
        } else {
            // Switching to PythonFunction to be able to get dependencies bundled for free
            // https://docs.aws.amazon.com/cdk/api/latest/docs/aws-lambda-python-readme.html
            // (If I wasn't so lazy, I would do this via a CodePipeline and CodeBuild instead)
            this.apiFunction = new PythonFunction(this, 'backend-lambda', {
                // pathToAssetCode is guaranteed defined by asssertExactlyOnePropertySet,
                // but TypeScript doesn't know that
                // (I could probably do this more idiomatically with a Type Guard,
                // but I'm still learning TypeScript!)
                entry: (props.pathToAssetCode as string),
                // It never hurts to have this as a reference so you can look up outputs!
                environment: {
                    'stackId': Fn.sub('${AWS::StackId}')
                },
                logRetention: RetentionDays.ONE_WEEK,
                runtime: Runtime.PYTHON_3_8,
            })
        }

        const externalLambda = new Function(this, 'external-lambda', {
            code: new AssetCode('lambda/external/'),
            environment: {
                stackId: Fn.sub('${AWS::StackId}'),
                apiFunctionArn: this.apiFunction.functionArn,
                staticSiteBucket: this.staticSiteBucket.bucketName
            },
            handler: 'index.handler',
            logRetention: RetentionDays.ONE_WEEK,
            runtime: Runtime.PYTHON_3_8
        })
        this.staticSiteBucket.grantRead(externalLambda)
        this.apiFunction.grantInvoke(externalLambda)

        // I wish there was a more direct way of doing this - that is, to have the domainName
        // for the apig and the Certificate explicitly reference the ARecord, rather than this string -
        // but it doesn't seem to be possible - https://stackoverflow.com/questions/66415361/circular-dependency-of-defining-apigateay-arecord-and-certificate
        const domainName = props.websiteDomainRecord + '.' + zone.zoneName

        let cert = new Certificate(this, 'cert', {
            domainName: domainName,
            validation: CertificateValidation.fromDns(zone)
        });

        const apig = new LambdaRestApi(this, 'api', {
            handler: externalLambda,
            proxy: true,
            deploy: true,
            domainName: {
                domainName: domainName,
                certificate: cert
            }
        })

        new ARecord(this, 'apiDNS', {
            zone: zone,
            recordName: props.websiteDomainRecord,
            target: RecordTarget.fromAlias(new ApiGateway(apig))
        })

    }

    private createStaticSiteResources(zone: IHostedZone, props: StaticWebsiteWithApiProps) {
        // Static site resources
        if (props.staticBucket == undefined) {
            this.staticSiteBucket = new Bucket(this, 'static-website-bucket', {
                bucketName: ((props.websiteDomainRecord != undefined) ? props.websiteDomainRecord + '.' : '') + props.rootDomain,
                publicReadAccess: true,
                removalPolicy: cdk.RemovalPolicy.DESTROY,
                websiteIndexDocument: props.websiteIndexDocument?? 'index.html'
            })
        } else {
            this.staticSiteBucket = props.staticBucket;
        }

        new BucketDeployment(this, 'deploy-static-website', {
            sources: [Source.asset(props.pathToStaticSiteSources)],
            destinationBucket: this.staticSiteBucket
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