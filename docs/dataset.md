# Dataset

18 documents: 7 `dev`, 11 `test`. Each document in `data/documents/` has a
ground truth file of the same base name in `data/ground_truth/`, labelled by
hand from the image following `docs/labeling-guide.md`.

- **`dev`** is used while tuning prompts.
- **`test`** is held back for the reported score. Those documents are run only
  twice, for the baseline and for the final version, and are never used for
  tuning. Their file names start with `test_`; the `split` field in the ground
  truth is what the harness reads.

## Documents

Source: where the document came from. Personal data: what is visible on the
image. Not redacted yet means the image is committed as photographed.

| File | Type | Split | Source | Personal data | Redacted |
|---|---|---|---|---|---|
| food_receipts01.jpeg | food | dev | TBD | – | – |
| food_receipts02.jpeg | retail | dev | TBD | – | – |
| food_receipts03.jpeg | food | dev | TBD | – | – |
| fuel_receipts01.jpg | fuel | dev | TBD | – | – |
| fuel_receipts02.jpg | fuel | dev | TBD | tagged `contains_personal_data` | TBD |
| invoice01.jpeg | retail | dev | TBD | tagged `contains_personal_data` | TBD |
| service_receipts01.jpg | vehicle_service | dev | TBD | customer name, phone, plate | not yet |
| test_food_receipts04.jpg | food | test | TBD | customer name | not yet |
| test_fuel_receipts03.jpg | fuel | test | TBD | plate | not yet |
| test_fuel_receipts04.jpg | fuel | test | TBD | – | – |
| test_invoice02.pdf | retail | test | Synthetic, made for this dataset; marked "SAMPLE DOCUMENT - FOR DATASET / TESTING USE" | – | – |
| test_service_note01.jpg | vehicle_service | test | TBD | customer name, plate | not yet |
| test_service_note02.jpg | vehicle_service | test | TBD | customer name, phone, plate, customer ID | not yet |
| test_service_note03.jpg | vehicle_service | test | TBD | customer name, plate, bank account number and holder | not yet |
| test_service_note04.jpg | vehicle_service | test | TBD | owner name, address, phone, plate, chassis number | not yet |
| test_service_note05.jpg | vehicle_service | test | TBD | customer name, address, phone, plate, frame number | not yet |
| test_service_note06.jpg | vehicle_service | test | TBD | customer name, phone, plate | not yet |
| test_service_note07.jpg | vehicle_service | test | TBD | customer name, address, phone, plate | not yet |

## Coverage

By `document_type` in the ground truth (`food_receipts02` is labelled
`retail`).

| Type | dev | test | total |
|---|---|---|---|
| food | 2 | 1 | 3 |
| fuel | 2 | 2 | 4 |
| retail | 2 | 1 | 3 |
| vehicle_service | 1 | 7 | 8 |
| **total** | **7** | **11** | **18** |

Handwritten: `invoice01` (dev), `test_service_note01` (test). Multi-page PDF:
`test_invoice02` (test).

## Known gaps

- **Redaction.** Personal data on the images listed above is not redacted yet.
  The plan is to cover names, phone numbers, addresses, plates, chassis/frame
  numbers and the bank account with solid boxes, without touching merchant,
  date, items or amounts, and to add the `contains_personal_data` tag to those
  ground truth files.
- **Small dev split for vehicle service.** One `dev` document against seven in
  `test`, so prompt changes are tuned on little service-note data.
- **One multi-page PDF**, and it is synthetic.
