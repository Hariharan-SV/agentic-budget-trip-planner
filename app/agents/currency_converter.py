
import requests
from typing import Dict, Any

def convert_currency(amount: float, from_currency: str, to_currency: str) -> Dict[str, Any]:
    """
    A tool to convert currency using a public exchange rate API.
    """
    if from_currency == to_currency:
        return {"status": "success", "converted_amount": amount}

    try:
        response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{from_currency}")
        if response.status_code != 200:
            return {"status": "failure", "reason": "Failed to fetch exchange rates."}

        data = response.json()
        rates = data.get("rates", {})
        rate = rates.get(to_currency)

        if rate is None:
            return {"status": "failure", "reason": f"Currency {to_currency} not supported."}

        return {"status": "success", "converted_amount": amount * rate}
    except Exception as e:
        return {"status": "failure", "reason": str(e)}
