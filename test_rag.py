import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config
from utils.tools import calculator, get_weather, convert_currency, get_stock_quote


def test_tools():
    print("=== Testing Tools ===")
    
    # 1. Calculator
    print("Testing calculator with '0.15 * 2.3e9'...")
    try:
        res = calculator("0.15 * 2.3e9")
        print("  calculator(0.15 * 2.3e9) ->", res)
    except Exception as e:
        print("  calculator failed:", e)

    print("Testing calculator with caret '10^3'...")
    try:
        res = calculator("10^3")
        print("  calculator(10^3) ->", res)
    except Exception as e:
        print("  calculator failed:", e)
        
    # 2. Weather
    print("Testing get_weather with 'London today'...")
    try:
        res = get_weather("London today")
        print("  get_weather('London today') ->", res)
    except Exception as e:
        print("  get_weather failed:", e)
        
    # 3. Currency conversion
    print("Testing convert_currency with '100', 'dollars', 'euros'...")
    try:
        res = convert_currency(100, "dollars", "euros")
        print("  convert_currency(100, 'dollars', 'euros') ->", res)
    except Exception as e:
        print("  convert_currency failed:", e)

    # 4. Stock quote
    print("Testing get_stock_quote with 'NVDA'...")
    try:
        res = get_stock_quote("NVDA")
        print("  get_stock_quote('NVDA') ->", res)
    except Exception as e:
        print("  get_stock_quote failed:", e)


def test_llm_connection():
    print("\n=== Testing LLM Connection ===")
    print("LLM Provider:", config.PROVIDER)
    print("LLM Base URL:", config.LLM_BASE_URL)
    print("LLM Heavy Model:", config.MODEL_HEAVY)
    
    from utils.llm import make_llm, invoke_text
    try:
        llm = make_llm(config.MODEL_HEAVY)
        res = invoke_text(llm, [{"role": "user", "content": "Explain agentic RAG in one short sentence."}])
        print("LLM Response:", res)
    except Exception as e:
        print("LLM connection failed:", e)


if __name__ == "__main__":
    test_tools()
    test_llm_connection()
