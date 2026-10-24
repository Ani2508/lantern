# infra/  (OWNER: M1 — DRAFT by M3 for M1 review)

`template.yaml` (SAM) creates everything in contract 2.4/2.6: 2 buckets, 4 DynamoDB tables,
SNS topic `lantern-dev-alerts`, Lambdas `lantern-dev-{simulate,ingest,plan,api}`, CloudFront.

```bash
make deploy        # build-src -> sam build -> sam deploy -> upload web files -> invalidate CloudFront
make destroy       # after judging
```

After the first deploy:
1. Copy `CloudFrontUrl` from the outputs into `.env` as `VITE_API_BASE_URL=<url>/api`.
2. Add it to `CORS_ORIGINS` on `lantern-dev-api`, and pass `FallbackUrl=<url>/fallback/` as a parameter.
3. Subscribe team phones/emails to `lantern-dev-alerts` (SMS sandbox: verify numbers first).
4. Upload the trained model: `LANTERN_MODE=aws make train` (needs features.csv in S3).

If the event account blocks parts of this:
- **No CloudFront** -> delete `Distribution`, `WebOAC`, `FallbackCachePolicy`, `WebBucketPolicy`;
  host the web bucket as an S3 static website and call the API Function URL directly.
- **No container images / ECR** -> make `PlanFunction` a zip with `CodeUri: ../.build/src` and add
  `numpy pandas xgboost` to a Lambda layer (or drop the forecaster: the engine falls back to stock/burn).
- **No SMS** -> subscribe email addresses to the topic instead.
- **No IAM users** -> everyone uses their own event login; only one person runs `make deploy`.
