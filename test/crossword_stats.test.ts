import { expect as expectCDK, matchTemplate, MatchStyle } from '@aws-cdk/assert';
import * as cdk from '@aws-cdk/core';
import * as CrosswordStats from '../lib/crossword_stats-stack';

test('Empty Stack', () => {
    const app = new cdk.App();
    // WHEN
    const stack = new CrosswordStats.CrosswordStatsStack(app, 'MyTestStack');
    // THEN
    expectCDK(stack).to(matchTemplate({
      "Resources": {}
    }, MatchStyle.EXACT))
});
