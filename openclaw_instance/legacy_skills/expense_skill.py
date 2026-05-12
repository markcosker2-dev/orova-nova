# -*- coding: utf-8 -*-
"""
Expense Tracker Skill for MarkBot
Log expenses, categorize them, and generate reports
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Expense data file
EXPENSES_FILE = Path(__file__).parent.parent / "expenses.json"

# Default expense categories
CATEGORIES = [
    "food", "transport", "utilities", "entertainment", 
    "shopping", "business", "health", "subscriptions", "other"
]


def _load_expenses():
    """Load expenses from file"""
    if EXPENSES_FILE.exists():
        try:
            with open(EXPENSES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []


def _save_expenses(expenses: list):
    """Save expenses to file"""
    with open(EXPENSES_FILE, 'w', encoding='utf-8') as f:
        json.dump(expenses, f, indent=2, ensure_ascii=False)


def add_expense(amount: float, description: str, category: str = "other"):
    """Add a new expense
    
    Args:
        amount: Amount spent (in your currency)
        description: What was the expense for
        category: Category (food, transport, utilities, etc.)
    """
    expenses = _load_expenses()
    
    # Normalize category
    category = category.lower()
    if category not in CATEGORIES:
        category = "other"
    
    expense = {
        "id": len(expenses) + 1,
        "amount": float(amount),
        "description": description,
        "category": category,
        "date": datetime.now().isoformat(),
        "month": datetime.now().strftime("%Y-%m")
    }
    
    expenses.append(expense)
    _save_expenses(expenses)
    
    return {
        "success": True,
        "message": f"Added expense: ${amount:.2f} for {description}",
        "expense": expense
    }


def list_expenses(limit: int = 20, category: str = None, month: str = None):
    """List expenses
    
    Args:
        limit: Max number to return
        category: Filter by category
        month: Filter by month (YYYY-MM format)
    """
    expenses = _load_expenses()
    
    # Apply filters
    if category:
        expenses = [e for e in expenses if e.get("category") == category.lower()]
    
    if month:
        expenses = [e for e in expenses if e.get("month") == month]
    
    # Sort by date descending
    expenses = sorted(expenses, key=lambda x: x.get("date", ""), reverse=True)
    
    # Calculate total
    total = sum(e.get("amount", 0) for e in expenses)
    
    return {
        "success": True,
        "total_amount": round(total, 2),
        "count": len(expenses),
        "expenses": expenses[:limit]
    }


def expense_report(period: str = "month"):
    """Generate expense report
    
    Args:
        period: "week", "month", or "year"
    """
    expenses = _load_expenses()
    now = datetime.now()
    
    # Filter by period
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "year":
        start_date = now.replace(month=1, day=1)
    else:  # month
        start_date = now.replace(day=1)
    
    start_str = start_date.isoformat()
    filtered = [e for e in expenses if e.get("date", "") >= start_str]
    
    # Sum by category
    by_category = defaultdict(float)
    for e in filtered:
        by_category[e.get("category", "other")] += e.get("amount", 0)
    
    # Sort by amount
    sorted_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    
    total = sum(by_category.values())
    
    # Format report
    breakdown = []
    for cat, amt in sorted_categories:
        pct = (amt / total * 100) if total > 0 else 0
        breakdown.append({
            "category": cat,
            "amount": round(amt, 2),
            "percentage": round(pct, 1)
        })
    
    return {
        "success": True,
        "period": period,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "total": round(total, 2),
        "transaction_count": len(filtered),
        "breakdown": breakdown
    }


def delete_expense(expense_id: int):
    """Delete an expense by ID"""
    expenses = _load_expenses()
    
    original_count = len(expenses)
    expenses = [e for e in expenses if e.get("id") != expense_id]
    
    if len(expenses) == original_count:
        return {"success": False, "error": f"Expense #{expense_id} not found"}
    
    _save_expenses(expenses)
    
    return {
        "success": True,
        "message": f"Expense #{expense_id} deleted"
    }


def register_expense_skills(TOOLS, tool_decorator):
    """Register Expense Tracker tools"""
    
    @tool_decorator("add_expense", "Log an expense")
    def _add_expense(**kwargs):
        amount = kwargs.get('amount') or kwargs.get('cost') or kwargs.get('price')
        description = kwargs.get('description') or kwargs.get('desc') or kwargs.get('for') or kwargs.get('item')
        category = kwargs.get('category') or kwargs.get('type') or "other"
        
        if not amount:
            return {"success": False, "error": "Missing 'amount' parameter"}
        if not description:
            return {"success": False, "error": "Missing 'description' parameter"}
        
        try:
            amount = float(str(amount).replace('$', '').replace(',', ''))
        except:
            return {"success": False, "error": "Invalid amount format"}
        
        return add_expense(amount, description, category)
    
    @tool_decorator("list_expenses", "List recent expenses")
    def _list_expenses(**kwargs):
        limit = kwargs.get('limit') or 20
        category = kwargs.get('category')
        month = kwargs.get('month')
        
        try:
            limit = int(limit)
        except:
            limit = 20
        
        return list_expenses(limit, category, month)
    
    @tool_decorator("expense_report", "Generate expense report")
    def _expense_report(**kwargs):
        period = kwargs.get('period') or kwargs.get('timeframe') or "month"
        if period not in ["week", "month", "year"]:
            period = "month"
        return expense_report(period)
    
    @tool_decorator("delete_expense", "Delete an expense")
    def _delete_expense(**kwargs):
        expense_id = kwargs.get('expense_id') or kwargs.get('id')
        if not expense_id:
            return {"success": False, "error": "Missing 'expense_id' parameter"}
        try:
            expense_id = int(expense_id)
        except:
            return {"success": False, "error": "expense_id must be a number"}
        return delete_expense(expense_id)
    
    TOOLS["add_expense"] = {"func": _add_expense, "description": "Log an expense"}
    TOOLS["list_expenses"] = {"func": _list_expenses, "description": "List expenses"}
    TOOLS["expense_report"] = {"func": _expense_report, "description": "Generate expense report"}
    TOOLS["delete_expense"] = {"func": _delete_expense, "description": "Delete an expense"}
    
    return TOOLS
