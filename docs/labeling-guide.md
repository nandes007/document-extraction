# Labelling guide

Ground truth is written and verified by a human. These rules keep the labels
consistent across documents.

## Rules

1. Label from the image, never from a model's output alone.
2. Merchant name is the brand without the branch.
3. A printed zero (`Diskon: 0`) is `present` with value 0.
4. Repeated rows stay as separate line items. Modifiers such as "LESS SWEET"
   are not items.
5. When tax is included in the price, record the stated tax; `total` is the
   amount paid.
6. Expand shorthand only when the document makes it unambiguous.
7. If a value cannot be read with confidence, mark it `unreadable`. If it is
   not on the document, mark it `not_present`.

## Rules added 2026-10-07 (after the first all-field review of run v1)

- **Subtotal.** Present only when the document has two or more money lines
  named as a total of the whole bill. The earlier one is `subtotal`; the
  amount the customer must pay (Grand Total, Net Amount) is `total`.
  Not totals: payment lines (Pembayaran, Tunai, Debit, GoPay, Kembalian),
  quantity totals (Total Quantity, Total 6 item), and category totals
  (Total Barang, Total Jasa).
- **Payment method.** Use `debit` or `credit` only when the receipt says so.
  A card payment that names only an EDC machine or a bank is `card`.
  Food delivery platforms (GoFood, GrabFood, ShopeeFood) are `other`.
- **Document type.** `food` is prepared food and drinks (restaurants, cafes).
  `retail` is goods bought from a shop, including groceries.

## Label changes

- 2026-10-07: `food_receipts02` document_type food -> retail (document type rule).