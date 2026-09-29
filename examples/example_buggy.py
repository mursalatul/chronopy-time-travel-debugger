"""
example_buggy.py — A deliberately buggy Python program for ChronoPy demos.

Run it under ChronoPy:
    chronopy record examples/example_buggy.py

Then open the UI, click on the wrong output, and trace the causal chain.
"""

import random
import time


def fibonacci(n):
    """Classic fib — but with an off-by-one bug when n == 0."""
    if n < 0:
        raise ValueError(f"fibonacci expects non-negative input, got {n}")
    if n == 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)


def collatz(n):
    """Collatz conjecture — how many steps to reach 1?"""
    steps = 0
    sequence = [n]
    while n != 1:
        if n % 2 == 0:
            n = n // 2
        else:
            n = 3 * n + 1
        sequence.append(n)
        steps += 1
        if steps > 1000:
            break
    return steps, sequence


def buggy_sort(arr):
    """Bubble sort with a deliberate bug: stops one iteration too early."""
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - i - 2):   # BUG: should be n - i - 1
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr


def process_data(data):
    """Process a list of numbers: filter, transform, aggregate."""
    filtered  = [x for x in data if x > 0]
    scaled    = [x * 2.5 for x in filtered]
    total     = sum(scaled)
    mean      = total / len(scaled) if scaled else 0
    maximum   = max(scaled) if scaled else None
    return {
        "filtered_count": len(filtered),
        "total":   total,
        "mean":    mean,
        "maximum": maximum,
    }


def run_demo():
    print("=== ChronoPy Demo — Buggy Program ===\n")

    # Fibonacci
    print("Fibonacci sequence:")
    for i in range(10):
        result = fibonacci(i)
        print(f"  fib({i}) = {result}")

    # Collatz
    print("\nCollatz steps:")
    for start in [6, 11, 27]:
        steps, seq = collatz(start)
        print(f"  collatz({start}) = {steps} steps, last 5: {seq[-5:]}")

    # Buggy sort
    data = [5, 3, 8, 1, 9, 2, 7, 4, 6]
    original = data[:]
    sorted_data = buggy_sort(data)
    print(f"\nBuggy sort of {original}:")
    print(f"  Result: {sorted_data}")
    print(f"  Sorted? {sorted_data == sorted(original)}")

    # Data processing
    raw = [-3, 0, 4, -1, 7, 2, -5, 8, 3, 0, 1]
    result = process_data(raw)
    print(f"\nData processing of {raw}:")
    for k, v in result.items():
        print(f"  {k}: {v}")

    # Intentional exception
    print("\nTriggering an exception…")
    try:
        bad = fibonacci(-5)
    except ValueError as e:
        print(f"  Caught: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    run_demo()
