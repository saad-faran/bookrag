#!/usr/bin/env python3
"""An example MCP server exposing finance calculators over the real MCP protocol (stdio).

BookRAG's MCP *client* connects to this (see server/mcp_client.py + mcp_config.json) and
makes these tools available to the agent — demonstrating third-party tool integration via
the Model Context Protocol. Add any other MCP server (official or your own) to
mcp_config.json and its tools are discovered automatically.

Run standalone:  python mcp_servers/finance_tools.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("bookrag-finance-tools")


@mcp.tool()
def compound_interest(principal: float, annual_rate_pct: float, years: float,
                      compounds_per_year: int = 12) -> dict:
    """Future value of an investment with compound interest. IMPORTANT: annual_rate_pct is a
    PERCENT NUMBER, not a decimal — pass 7 for 7% (never 0.07). principal is the starting
    amount in currency units; years is the horizon."""
    r = annual_rate_pct / 100.0
    n = max(1, int(compounds_per_year))
    fv = principal * (1 + r / n) ** (n * years)
    return {
        "principal": round(principal, 2),
        "annual_rate_pct": annual_rate_pct,
        "years": years,
        "future_value": round(fv, 2),
        "interest_earned": round(fv - principal, 2),
        "formatted": f"{round(fv, 2):,.2f}",
    }


@mcp.tool()
def rule_of_72(annual_rate_pct: float) -> dict:
    """Approximate years for an investment to double at a given annual return (Rule of 72).
    annual_rate_pct is a PERCENT NUMBER — pass 8 for 8% (never 0.08)."""
    if annual_rate_pct <= 0:
        return {"error": "annual_rate_pct must be > 0"}
    return {"annual_rate_pct": annual_rate_pct,
            "years_to_double": round(72 / annual_rate_pct, 1)}


@mcp.tool()
def loan_payment(principal: float, annual_rate_pct: float, years: float) -> dict:
    """Monthly payment, total paid and total interest for an amortizing loan (e.g. a mortgage).
    annual_rate_pct is a PERCENT NUMBER — pass 6.5 for 6.5% (never 0.065)."""
    n = max(1, int(years * 12))
    r = annual_rate_pct / 100.0 / 12.0
    pmt = principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)
    return {
        "principal": round(principal, 2),
        "annual_rate_pct": annual_rate_pct,
        "years": years,
        "monthly_payment": round(pmt, 2),
        "total_paid": round(pmt * n, 2),
        "total_interest": round(pmt * n - principal, 2),
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
