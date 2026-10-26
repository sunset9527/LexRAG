# Stage 8 review workflow

Stage 8 starts with a 300-row candidate review queue: 100 existing legacy seed
rows plus 200 newly proposed hard candidates. This queue is pending-only and is
not a frozen or formal evaluation dataset.

For each row, a human reviewer checks the question, proposed question type and
difficulty, knowledge-base scope, relevant article IDs, abstention decision, and
local source locator. The reviewer records their name, timestamp, and review
note, then materializes a separately verified/approved row.

Only those separately materialized approved rows, with complete human review
evidence, may become the formal frozen Stage 8 dataset. Candidate queue rows
must not be used as formal evaluation evidence or to make performance claims.
