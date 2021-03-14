# NYT Mini Crossword Stats

The [NYTimes Mini Crossword](https://www.nytimes.com/crosswords/game/mini)
is a fun part of my morning routine, but it bugged me that there's no history
on the Leaderboard - so I made one!

This repo uses [CDK](https://aws.amazon.com/cdk/) to define a system that regularly
polls the Leaderboard to fetch your group's scores and
provides a web interface to view a graph of them.

See `ARCHITECTURE.md` for more info. PRs welcome!

# How to set up your own version

## Prerequisites

* [Docker](https://www.docker.com/products/docker-desktop) and [CDK](https://aws.amazon.com/cdk/)
    installed locally
* An AWS Account, where you have a Route53 Domain defined
* A locally-defined [AWS CLI profile](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html)
    that has Cloudformation CreateStack permissions (and probably others - please cut an Issue or make a PR
    if you go to the effort of determining Least Privilege!)
* Greasemonkey (only tested on Firefox - there's no reason this wouldn't work with Tampermonkey,
    so long as it supports the `GM.[set|get]Value` [methods](https://wiki.greasespot.net/GM.setValue))

## Steps

1. Check out this repo locally
2. Change the `rootDomain` argument to `StaticWebsiteWithApi` in `crossword_stats-stack.ts`
    to your Route53 Domain (TODO - make this a parameter rather than hard-coded)
3. Run `$ cdk deploy --profile <profile_from_prerequisites>` to deploy the system
    (TODO: a proper CodePipeline for deployment)
4. Confirm that `https://crossword.<your_domain>` loads (don't expect data yet!)
5. Install the `nyt-cookie-update.user.js` script to your *Monkey (it's served from
    the static site at `/nyt-cookie-update.user.js`)
6. Navigate to [the mini Crossword page](https://www.nytimes.com/crosswords/game/mini) -
    You should get a prompt saying "What is the score tracking domain?". Enter your full domain,
    with the `crossword` prefix (no `https://`)
7. That's it! Your system should be set up and working! It polls for data every 5 minutes,
    so check back for graphed scores in a little while.
