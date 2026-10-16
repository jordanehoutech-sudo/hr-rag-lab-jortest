# How the pipeline helpers fit together

The helpers are provided. We connect them through GitHub Actions, configure the test cases and release rules, and interpret the results. We do not need to write every helper from scratch.

## Main delivery path

| Stage | Prepared helper | What we verify |
|---|---|---|
| Package | `release.py` | Prompt format, numbered Langfuse version and exact release identity |
| Deploy candidate | `deploy_candidate.py` | The intended package reaches the staging Lambda version |
| Evaluate API | `evaluate_api.py` | Authenticated test users receive correct, authorized answers |
| Report | `report.py` | All required cases completed and the results are recorded |
| Approve release | `promote_lab.py` | Only the exact passing release moves the approved staging pointer |

## Four views of answer quality

- Promptfoo checks required facts, prohibited facts and sources in the captured API answers.
- Langfuse records the dataset experiment and scores by release so we can compare results.
- DeepEval grades the answer against approved reference outcomes; disagreements need review.
- Evidently compares numeric answer-length and latency patterns. A shift prompts investigation, not an automatic verdict that an answer is wrong.

The prepared adapters connect these tools to the same captured API results. We configure their workflow blocks rather than rewrite the adapters.

## Supporting automation

`auth.py` is used internally by the API evaluator. It reads dedicated test credentials from Secrets Manager, signs in through Cognito and obtains fresh tokens. This runs on each evaluation; creating the users during setup does not supply permanent tokens.

`deploy_frontend.py` uploads the built React files to S3 and refreshes CloudFront. `rollback_lab.py` restores a previous approved pointer within staging. `tests/` verifies prompt structure, release packaging, judge behavior and trace handling.

## Additional analysis

Alternative local drift reporting, version comparisons and human-versus-model agreement are kept in [examples/evaluation](../examples/evaluation/README.md). They are not extra required pipeline stages.

## Does the workflow need these files?

**Yes, the workflow calls most of these helpers directly or through an Action.** They are inputs and application-specific operations, not second implementations of the tools.

| File we see | Its job | What the Action does instead |
|---|---|---|
| `evaluate_api.py` | Signs in test identities, calls our authenticated HR API, checks expected facts and records answers | No supplied tool Action performs this complete HR-specific API and authorization test |
| `prepare_promptfoo.py` | Converts approved cases into Promptfoo configuration | Promptfoo Action executes that configuration |
| `promptfoo-provider.cjs` | Reads the captured API answers for the configured cases | Promptfoo Action uses that provider to run assertions |
| `prepare_drift.py` | Checks dataset compatibility and writes numeric measurements to CSV | Evidently Action compares the CSV with the reference and generates the report |
| `evidently_config.py` | Declares the report metrics; it does not run the report | Evidently Action loads this configuration and runs it |
| `langfuse_experiment.py` | Defines the dataset experiment using our captured answers and reference checks | Langfuse Action executes that experiment and publishes its results |
| `promote_lab.py` | Checks release identity and passing evidence before updating the approved staging alias | Evaluation Actions do not decide or perform our AWS release operation |

The workflow uses `auth.py` through `evaluate_api.py`; configuration files and providers can be required even without a separate `run: python` step. `rollback_lab.py` is recovery support, not a normal pipeline step. `check_promptfoo.py` is currently **not called** by the supplied workflow; the Promptfoo Action enforces its own configured failure threshold. Do not add another step for it unless a separate completeness check is required.

## Why Actions still call helpers

GitHub Actions supplies the runner and connects the stages. The prepared workflow uses the official Promptfoo, Langfuse experiment and Evidently report Actions. DeepEval runs through a prepared Python command. These integrations run the tools, but still need application-specific inputs: how to authenticate, which API to call, which answers to check and which AWS version to release.

We do not recreate those tools in Python. The adapters translate our captured API answers and approved references into each tool's format. Deployment helpers implement this application's release rules. We configure the workflow and test cases; the supplied helpers execute those rules.

## Every file and why it exists

| File | What it does | Why it exists / when it runs |
|---|---|---|
| `release.py` | Checks the prompt, publishes its numbered Langfuse version when requested, and packages Python with a release manifest | Bind prompt and code to an identifiable release before deployment |
| `deploy_candidate.py` | Uploads the backend package, publishes an immutable Lambda version and moves the candidate alias | Deploy the exact proposed staging release |
| `deploy_frontend.py` | Uploads the built React site and invalidates CloudFront | Release frontend changes alongside the backend |
| `auth.py` | Gets fresh Cognito tokens for dedicated synthetic identities | An authenticated API test needs a current token, not just an account created during setup |
| `evaluate_api.py` | Calls the real API for every case and repetition, checks authorization, reference facts and release identity | Produce the application's live test evidence |
| `report.py` | Checks result completeness and writes a report without raw employee answers | Make release evidence safe to retain and inspect |
| `prepare_promptfoo.py` | Generates Promptfoo inputs and assertions from captured results and reference cases | Adapt our data to the official Promptfoo Action |
| `promptfoo-provider.cjs` | Supplies the captured answer to Promptfoo | Check an existing API answer without paying to generate it again |
| `check_promptfoo.py` | Checks complete case coverage and no failures/errors | Not called by the supplied workflow; retained as a separate diagnostic check |
| `langfuse_experiment.py` | Publishes dataset items and records captured answers and scores as an experiment | Give the official Langfuse Action our application-specific experiment |
| `deepeval_check.py` | Uses a Bedrock-backed DeepEval grader against reference outcomes | Demonstrate an independent model-based grading pattern |
| `prepare_drift.py` | Converts baseline/current results into numeric proxy measurements | Feed the Evidently Action without exporting answer text in its input |
| `evidently_config.py` | Defines the Evidently report metrics | Configure what the official report Action measures |
| `promote_lab.py` | Checks passing evidence before moving the approved staging alias | Prevent approval of an untested or mismatched version; does not deploy production |
| `rollback_lab.py` | Restores the recorded previous approved staging version | Demonstrate recovery without deleting infrastructure |
| `requirements.txt` | Lists core helper dependencies | Install the delivery/evaluation runtime |
| `requirements-demo.txt` | Lists dependencies for the additional evaluation tools | Install the enabled tool demonstrations |
| `tests/` | Checks packaging, prompt structure, judge behavior and telemetry handling | Catch implementation regressions before cloud deployment |

## Where the outputs go

Helpers create the ignored `build/` directory when needed. Packaging writes `function.zip` and `release.json`; live evaluation writes `evaluation.json`; reporting writes report files. Local runs create these on the workstation. Actions runs create them in that job's runner workspace.

Jobs do not automatically share their filesystem. Only explicitly uploaded/downloaded artifacts transfer between jobs or remain available after the runner is removed. The workflow retains selected release/report artifacts and excludes raw evaluation answers from the uploaded artifact bundle.

## Data and tests folders

`data/` contains inputs, not another evaluation engine:

- `drift-reference.csv`: captured numeric answer-length and latency measurements that the Evidently Action compares with the current run.
- `drift-reference.json`: provenance and the case-definition hash used by `prepare_drift.py` to reject an incompatible comparison. The supplied reference is a synthetic failing run for demonstrating change detection, not an approved production-quality baseline.

`tests/` contains local implementation checks run by the branch/PR job:

- `test_release.py`: prompt validation, release packaging and inline-judge behavior.
- `test_gateway.py`: model-request translation, approved models, denied allowances, and no direct-provider escape path.
- `test_telemetry.py`: trace context, user/session handling and sensitive-data protection.

These unit tests check the helpers and application plumbing. The live API evaluation checks deployed behavior. Tool Actions add their configured views of the captured answers. Those stages have different inputs and purposes; running them is not running the same implementation twice.

The application gateway adapter is in `lambda/app/model_gateway.py`; its service and database setup belong to infrastructure/bootstrap, not a duplicate evaluation Action. DeepEval invokes the gateway-backed evaluation Lambda rather than calling Bedrock directly. See [gateway controls](../docs/HR-LAB-START-TO-FINISH.md#gateway-implementation).
