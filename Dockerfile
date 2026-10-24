FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}
COPY pyproject.toml ./
COPY lantern_core lantern_core
COPY api api
COPY simulator simulator
COPY ingest ingest
COPY baselines baselines
COPY eval eval
COPY engine engine
COPY models models
COPY gate gate
COPY explain explain
COPY alerts alerts
COPY tests/fixtures tests/fixtures
RUN pip install --no-cache-dir .

CMD ["api.app.handler"]
