# Update Fashion Mart

Static storefront starter for InfinityFree. Upload `index.html` and `admin.html` to the domain's `htdocs` directory.

## Important setup notes
- In `index.html`, replace `SHOP_WHATSAPP='8801XXXXXXXXX'` with the store WhatsApp number (country code, digits only).
- Product gallery supports multiple image URLs per item.
- The demo admin uses browser localStorage only. It is not secure and changes do not sync across visitors/devices. For production, implement PHP + MySQL, server-side authentication, image uploads, and order storage before accepting live orders.
- Replace the sample image URLs and product copy with the store's real catalogue.
