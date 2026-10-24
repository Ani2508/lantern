# lantern-dev-plan as a container image (numpy + pandas + xgboost exceed the 250 MB zip limit).
# OWNER: M3. Built by `sam build` (DockerContext = repo root). arm64 to match the template.
FROM public.ecr.aws/lambda/python:3.12-arm64

RUN pip install --no-cache-dir \
      "pydantic>=2.6" "pydantic-settings>=2.2" "python-dotenv>=1.0" \
      "numpy>=1.26" "pandas>=2.1" "xgboost>=2.0"

COPY lantern_core ${LAMBDA_TASK_ROOT}/lantern_core
COPY engine       ${LAMBDA_TASK_ROOT}/engine
COPY baselines    ${LAMBDA_TASK_ROOT}/baselines
COPY gate         ${LAMBDA_TASK_ROOT}/gate
COPY explain      ${LAMBDA_TASK_ROOT}/explain
COPY alerts       ${LAMBDA_TASK_ROOT}/alerts

CMD ["engine.handler.lambda_handler"]
