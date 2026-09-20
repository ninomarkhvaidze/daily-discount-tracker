import os
import requests
import resend

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from openai import OpenAI

load_dotenv()
USER_PROFILE = {
    "height_cm": os.getenv("USER_HEIGHT_CM"),
    "chest_cm": os.getenv("USER_CHEST_CM"),
    "waist_cm": os.getenv("USER_WAIST_CM"),
    "hips_cm": os.getenv("USER_HIPS_CM"),
    "usual_clothing_size": os.getenv("USER_CLOTHING_SIZE", "S"),
    "preferred_fit": os.getenv("USER_PREFERRED_FIT", "regular")
}

resend.api_key = os.getenv("RESEND_API_KEY")

openai_api_key = os.getenv("OPENAI_API_KEY")

print("Resend API key loaded:", bool(resend.api_key))
print("OpenAI API key loaded:", bool(openai_api_key))

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

            # Shoes: only EU size 39
            if product["product_type"] == "ZAPATILLAS":
                if variant["title"] != "39":
                    continue

            # Clothing: only size S
            else:
                if variant["title"] != "S":
                    continue

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
                    "product_type": product["product_type"],
                    "price": variant["price"],
                    "was": variant["compare_at_price"],
                    "discount_pct": discount_percentage,
                    "url": (
                        f"{BASE_URL}/en/products/"
                        f"{product['handle']}"
                    )
                })

    return discounts


def clean_html(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text(" ", strip=True)


def prepare_clothing_for_ai(products, discounts):
    discounted_products = {
        item["product"]
        for item in discounts
        if item["product_type"] != "ZAPATILLAS"
    }

    clothing = []

    for product in products:
        if product["title"] not in discounted_products:
            continue

        # Only include products where S is available
        available_sizes = [
            variant["title"]
            for variant in product["variants"]
            if variant["available"] and variant["title"] == "S"
        ]

        if not available_sizes:
            continue

        clothing.append({
            "product": product["title"],
            "type": product["product_type"],
            "description": clean_html(product["body_html"]),
            "available_sizes": available_sizes,
            "url": f"{BASE_URL}/en/products/{product['handle']}"
        })

    return clothing


def get_ai_recommendation(item):
    """
    AI analyzes the product's fit/cut and evaluates
    whether the available S is likely to suit the user.

    If the API is unavailable, the program continues
    and the normal discount email is still sent.
    """

    if not openai_api_key:
        print("OpenAI API key is not available.")
        return None

    try:
        client = OpenAI(api_key=openai_api_key)

        prompt = f"""
You are a clothing fit assistant.

Your task is NOT to choose a size.
Python has already determined that size S is available.

Your task is to analyze whether this particular S-sized garment
is likely to suit the shopper's body measurements and preferred fit.

SHOPPER:
Height: {USER_PROFILE['height_cm']} cm
Chest: {USER_PROFILE['chest_cm']} cm
Waist: {USER_PROFILE['waist_cm']} cm
Hips: {USER_PROFILE['hips_cm']} cm
Usual clothing size: {USER_PROFILE['usual_clothing_size']}
Preferred fit: {USER_PROFILE['preferred_fit']}

PRODUCT:
Name: {item['product']}
Type: {item['type']}
Available size: S

PRODUCT DESCRIPTION:
{item['description']}

Analyze the product description for useful fit information.

Pay particular attention to words or indications such as:
- oversized
- loose
- relaxed
- regular
- slim
- fitted
- cropped
- wide
- straight
- tight
- boxy
- unisex
- stretchy
- rigid
- lightweight
- heavy
- structured

Do NOT invent garment measurements that are not provided.

If the description contains no useful fit information,
say that clearly.

Return exactly this format:

Fit assessment: [likely suitable / may be loose / may be tight / uncertain]
Confidence: [high / medium / low]
Reason: [1-3 short sentences explaining why]
Fit note: [short practical note about the cut or style]
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        return response.output_text.strip()

    except Exception as error:
        print("AI request failed:", error)
        return None


if __name__ == "__main__":

    products = fetch_all_products(BASE_URL)
    print(f"Fetched {len(products)} products.")

    discounts = find_discounts(products)
    print(f"Found {len(discounts)} discounted variants.")

    clothing_for_ai = prepare_clothing_for_ai(
        products,
        discounts
    )

    print()
    print("========== AI FIT TEST ==========")
    print(f"Clothing products with available S: {len(clothing_for_ai)}")
    print()

    # Test AI with ONE product only
    if clothing_for_ai:

        test_item = clothing_for_ai[0]

        print("Testing AI with:", test_item["product"])
        print("Available sizes:", test_item["available_sizes"])
        print("Description:", test_item["description"][:500])
        print()

        recommendation = get_ai_recommendation(test_item)

        if recommendation:
            print("AI FIT ASSESSMENT:")
            print(recommendation)
        else:
            print("AI fit assessment unavailable.")
            print("The normal discount email will still be sent.")

    print()
    print("========== END AI FIT TEST ==========")
    print()

    # Create the normal email digest
    from collections import defaultdict

    grouped = defaultdict(list)

    for item in discounts:
        grouped[item["product"]].append(item)

    digest = ""

    for product, items in grouped.items():

        first = items[0]

        sizes = [
            item["variant"]
            for item in items
        ]

        digest += (
            f"{product}\n"
            f"{first['price']} (was {first['was']}) | "
            f"{first['discount_pct']}% off\n"
            f"Sizes: {', '.join(sizes)}\n"
            f"Link: {first['url']}\n\n"
        )

    print("Sending email...")

    response = resend.Emails.send({
        "from": "Morrison Discounts <onboarding@resend.dev>",
        "to": "nmarkhvaidze@gmail.com",
        "subject": "Morrison Shoes — Daily Discounts",
        "text": digest
    })

    print("Email sent!")
    print(response)