"""School marks calculator.

Each subject mark is supposed to be between 0 and 100.
"""


def calculate(marks):
    """Return the total, percentage and grade for one student."""
    total = 0
    for mark in marks:
        total = total + mark
    percentage = total / len(marks)
    if percentage >= 90:
        grade = "A+"
    elif percentage >= 75:
        grade = "A"
    elif percentage >= 60:
        grade = "B"
    elif percentage >= 40:
        grade = "C"
    else:
        grade = "F"
    return {"total": total, "percentage": percentage, "grade": grade}


def main():
    """Print a result for an ordinary mark sheet."""
    print(calculate([70, 80, 90]))


if __name__ == "__main__":
    main()
