import os
import requests
import resend
from dotenv import load_dotenv
load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")
print("API key loaded:", bool(resend.api_key))

BASE_URL = "https://morrisonshoes.com"


def fetch_all_products(base_url):
    products = []
    page = 1

    while True:
        response = requests.get(
            f"{base_url}/products.json",
            params={"limit": 250, "page": page}
        )

        response.raise_for_status()

        data = response.json()["products"]

        if not data:
            break

        products.extend(data)
        page += 1

    return products


def find_discounts(products):
    discounts = []

    for product in products:
        for variant in product["variants"]:

            if (
                variant["compare_at_price"]
                and float(variant["compare_at_price"]) > float(variant["price"])
            ):
                discount_percentage = round(
                    (
                        1
                        - float(variant["price"])
                        / float(variant["compare_at_price"])
                    )
                    * 100
                )

                discounts.append({
                    "product": product["title"],
                    "variant": variant["title"],
                    "price": variant["price"],
                    "was": variant["compare_at_price"],
                    "discount_pct": discount_percentage,
                    "url": (
                        f"{BASE_URL}/en/products/"
                        f"{product['handle']}"
                    )
                })

    return discounts


if __name__ == "__main__":
    products = fetch_all_products(BASE_URL)

    print(f"Fetched {len(products)} products.")

    discounts = find_discounts(products)

    print(f"Found {len(discounts)} discounted variants.")

    from collections import defaultdict

grouped = defaultdict(list)

for item in discounts:
    grouped[item["product"]].append(item)

digest = ""

for product, items in grouped.items():
    first = items[0]

    sizes = [item["variant"] for item in items]

    digest += (
        f"{product}\n"
        f"{first['price']} (was {first['was']}) | "
        f"{first['discount_pct']}% off\n"
        f"Sizes: {', '.join(sizes)}\n"
        f"Link: {first['url']}\n\n"
    )

print(digest)
response = resend.Emails.send({
    "from": "onboarding@resend.dev",
    "to": "nmarkhvaidze@gmail.com",
    "subject": "Morrison Shoes — Daily Discounts",
    "text": digest
})

print("Email sent!")
print(response)