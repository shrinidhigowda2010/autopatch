"""Plain-language explanations for every rule, including a student version
and short Kannada and Hindi translations used when Gemini is offline.
"""

from __future__ import annotations

REVIEW_BELOW = 0.8

CATALOG: dict[str, dict] = {
    "marks_out_of_range": {
        "title": "Negative marks and marks over 100 are accepted",
        "category": "input_validation",
        "severity": "high",
        "confidence": 0.90,
        "impact": "A student can be given the wrong total, percentage and grade. One bad mark changes the result the school records.",
        "root_cause": "The loop adds every number it is given. Nothing checks the rule that a subject mark has to be between 0 and 100, so a negative mark or a mark above 100 still changes the total, the percentage and the grade.",
        "trigger": "Enter a mark below 0 or above 100, for example -5 or 150, and calculate the result.",
        "student": "The program trusts every number you type. If someone types -5 or 150, it still prints a grade, even though those are not real marks out of 100.",
        "kn": "ಈ ಪ್ರೋಗ್ರಾಂ ನೀವು ಟೈಪ್ ಮಾಡಿದ ಪ್ರತಿ ಸಂಖ್ಯೆಯನ್ನು ನಂಬುತ್ತದೆ. -5 ಅಥವಾ 150 ಎಂದು ಕೊಟ್ಟರೂ ಅದು ಶ್ರೇಣಿಯನ್ನು ಮುದ್ರಿಸುತ್ತದೆ. ನಿಜವಾದ ಅಂಕ 0 ರಿಂದ 100 ರ ಒಳಗೆ ಇರಬೇಕು.",
        "hi": "यह प्रोग्राम आपके लिखे हर अंक पर भरोसा कर लेता है। -5 या 150 देने पर भी यह ग्रेड छाप देता है, जबकि असली अंक 0 से 100 के बीच ही होना चाहिए।",
        "description": "Subject marks are summed with no range check, so values outside 0–100 still produce a grade.",
    },
    "empty_collection_divisor": {
        "title": "Empty input crashes with division by zero",
        "category": "crash",
        "severity": "high",
        "confidence": 0.93,
        "impact": "The program stops with ZeroDivisionError instead of telling the user what went wrong.",
        "root_cause": "The result is computed by dividing by the length of the collection. When the collection is empty that length is 0, and Python raises ZeroDivisionError before a result can be returned.",
        "trigger": "Call the function with an empty list.",
        "student": "If you press calculate without typing any numbers, the program crashes. It tries to divide by how many numbers you gave, and that count is zero.",
        "kn": "ಯಾವುದೇ ಸಂಖ್ಯೆಯನ್ನು ಕೊಡದೆ ಲೆಕ್ಕ ಮಾಡಿದರೆ ಪ್ರೋಗ್ರಾಂ ನಿಲ್ಲುತ್ತದೆ. ಅದು ಸಂಖ್ಯೆಗಳ ಎಣಿಕೆಯಿಂದ ಭಾಗಿಸುತ್ತದೆ, ಆ ಎಣಿಕೆ ಸೊನ್ನೆ ಆಗಿರುತ್ತದೆ.",
        "hi": "बिना कोई संख्या दिए गणना करने पर प्रोग्राम रुक जाता है। वह संख्याओं की गिनती से भाग देता है, और वह गिनती शून्य होती है।",
        "description": "A division uses the length of a collection that may be empty.",
    },
    "parameter_divisor": {
        "title": "Division by a value that can be zero",
        "category": "crash",
        "severity": "high",
        "confidence": 0.86,
        "impact": "Any caller that passes zero crashes the function with ZeroDivisionError.",
        "root_cause": "The function divides by a parameter and never checks that the parameter is not zero. The crash happens at the division itself, not in the caller.",
        "trigger": "Pass 0 as the divisor.",
        "student": "If the second number is 0, the program crashes. Dividing by zero is not allowed, and this function does not stop you.",
        "kn": "ಎರಡನೇ ಸಂಖ್ಯೆ 0 ಆದರೆ ಪ್ರೋಗ್ರಾಂ ನಿಲ್ಲುತ್ತದೆ. ಸೊನ್ನೆಯಿಂದ ಭಾಗಿಸಲು ಆಗುವುದಿಲ್ಲ, ಈ ಕಾರ್ಯ ಅದನ್ನು ತಡೆಯುವುದಿಲ್ಲ.",
        "hi": "दूसरी संख्या 0 होने पर प्रोग्राम रुक जाता है। शून्य से भाग नहीं हो सकता, और यह फ़ंक्शन उसे रोकता नहीं है।",
        "description": "A parameter is used as a divisor without a zero check.",
    },
    "deposit_non_positive": {
        "title": "Deposit accepts zero and negative amounts",
        "category": "logic",
        "severity": "high",
        "confidence": 0.90,
        "impact": "A negative deposit quietly reduces the balance. The account can be drained without a withdrawal.",
        "root_cause": "deposit adds the amount straight onto the balance. A negative amount is still added, which subtracts money, and zero is accepted as a deposit.",
        "trigger": "Deposit a negative amount, for example -50.",
        "student": "Putting in a minus number takes money out of the account. A deposit should only add money.",
        "kn": "ಋಣ ಸಂಖ್ಯೆಯನ್ನು ಠೇವಣಿ ಮಾಡಿದರೆ ಖಾತೆಯಿಂದ ಹಣ ಕಡಿಮೆಯಾಗುತ್ತದೆ. ಠೇವಣಿ ಹಣವನ್ನು ಸೇರಿಸಬೇಕೇ ಹೊರತು ಕಳೆಯಬಾರದು.",
        "hi": "ऋण राशि जमा करने पर खाते से पैसे घट जाते हैं। जमा में सिर्फ पैसे जुड़ने चाहिए।",
        "description": "deposit() updates the balance without requiring a positive amount.",
    },
    "withdraw_overdraft": {
        "title": "Withdrawal can drive the balance below zero",
        "category": "logic",
        "severity": "critical",
        "confidence": 0.92,
        "impact": "The account can go negative. A later report will show money the customer does not have.",
        "root_cause": "withdraw subtracts the amount from the balance and never compares it with the money that is actually there. Any amount, even more than the balance, succeeds.",
        "trigger": "Withdraw more than the current balance.",
        "student": "You can take out more money than the account holds. The balance just becomes a minus number.",
        "kn": "ಖಾತೆಯಲ್ಲಿರುವುದಕ್ಕಿಂತ ಹೆಚ್ಚು ಹಣ ತೆಗೆಯಬಹುದು. ಶೇಷ ಋಣ ಸಂಖ್ಯೆಯಾಗುತ್ತದೆ.",
        "hi": "खाते में जितना है उससे ज़्यादा पैसा निकाला जा सकता है। शेष राशि ऋण हो जाती है।",
        "description": "withdraw() subtracts from the balance with no funds check.",
    },
    "sql_injection": {
        "title": "Login query is built with string formatting",
        "category": "security",
        "severity": "critical",
        "confidence": 0.97,
        "impact": "Someone can change the query and log in without the password, or read rows they should not see.",
        "root_cause": "The username and password are pasted into the SQL text. The database then runs that text as code. A quote in the username can close the string early and add a condition that is always true.",
        "trigger": "Use a username like nobody' OR '1'='1 with any password.",
        "student": "The program glues whatever you type into the database question. A carefully typed username can trick the question into saying yes.",
        "kn": "ನೀವು ಟೈಪ್ ಮಾಡಿದ್ದನ್ನು ಪ್ರೋಗ್ರಾಂ ಡೇಟಾಬೇಸ್ ಪ್ರಶ್ನೆಯೊಳಗೆ ಅಂಟಿಸುತ್ತದೆ. ಹೀಗೆ ಟೈಪ್ ಮಾಡಿದ ಬಳಕೆದಾರ ಹೆಸರು ಪಾಸ್‌ವರ್ಡ್ ಇಲ್ಲದೆ ಒಳಗೆ ಬರಬಹುದು.",
        "hi": "प्रोग्राम आपके लिखे हुए को डेटाबेस के सवाल में चिपका देता है। ऐसे लिखे गए नाम से बिना पासवर्ड के अंदर घुसा जा सकता है।",
        "description": "User input is interpolated into a SQL statement instead of being passed as a bound parameter.",
    },
    "hardcoded_secret": {
        "title": "Secret is written directly in the source",
        "category": "security",
        "severity": "critical",
        "confidence": 0.94,
        "impact": "Anyone who can read the file, the zip or the git history can use this credential.",
        "root_cause": "The secret is a string literal assigned in code. It ships with the program instead of being read from the environment, where it can stay out of the repository.",
        "trigger": "Open the file, or search the project for the variable name. No special input is required.",
        "student": "The password is sitting in the file in plain text. Anyone who gets the code gets the password too.",
        "kn": "ಗುಪ್ತಪದ ಫೈಲಿನಲ್ಲಿ ಸ್ಪಷ್ಟವಾಗಿ ಬರೆದಿದೆ. ಕೋಡ್ ಸಿಕ್ಕವರಿಗೆ ಗುಪ್ತಪದವೂ ಸಿಗುತ್ತದೆ.",
        "hi": "पासवर्ड फ़ाइल में साफ़ लिखा है। जिसे कोड मिल गया, उसे पासवर्ड भी मिल गया।",
        "description": "A password, token or API key is hardcoded instead of being loaded from the environment.",
    },
    "mutable_default_argument": {
        "title": "Mutable default argument is shared between calls",
        "category": "logic",
        "severity": "high",
        "confidence": 0.98,
        "impact": "Later calls see items added by earlier calls. The bug shows up only when the caller skips the argument.",
        "root_cause": "Python builds a default list, dict or set once, when the function is defined, and reuses that same object on every call that does not pass the argument. Appending therefore changes the default for the next caller.",
        "trigger": "Call the function twice without passing the container. The second result still contains the first item.",
        "student": "The empty basket is created only once. The next person who does not bring their own basket gets the previous person's items.",
        "kn": "ಖಾಲಿ ಬುಟ್ಟಿಯನ್ನು ಒಮ್ಮೆ ಮಾತ್ರ ತಯಾರಿಸಲಾಗುತ್ತದೆ. ತಮ್ಮ ಬುಟ್ಟಿ ತರದ ಮುಂದಿನವರಿಗೆ ಹಿಂದಿನವರ ವಸ್ತುಗಳೇ ಸಿಗುತ್ತವೆ.",
        "hi": "खाली टोकरी सिर्फ एक बार बनती है। जो अगला व्यक्ति अपनी टोकरी नहीं लाता, उसे पिछले वाले की चीज़ें मिलती हैं।",
        "description": "A list, dict or set is used as a default argument and then mutated.",
    },
    "off_by_one_neighbor": {
        "title": "Loop reads one past the end of the list",
        "category": "crash",
        "severity": "high",
        "confidence": 0.90,
        "impact": "Every non-empty call raises IndexError on the last item. Callers never get a full result.",
        "root_cause": "The loop walks every index of the list and then reads the next item as well. On the last index that next item does not exist, so Python raises IndexError.",
        "trigger": "Pass a list with two or more numbers. The crash is on the final pair, not the first.",
        "student": "The loop looks at the next number after the last one. That number is not there, so the program crashes at the end of the list.",
        "kn": "ಕೊನೆಯ ಸಂಖ್ಯೆಯ ನಂತರ ಇನ್ನೊಂದು ಸಂಖ್ಯೆಯನ್ನು ಲೂಪ್ ಹುಡುಕುತ್ತದೆ. ಅದು ಇಲ್ಲ, ಆದ್ದರಿಂದ ಪಟ್ಟಿ ಮುಗಿದಾಗ ಪ್ರೋಗ್ರಾಂ ನಿಲ್ಲುತ್ತದೆ.",
        "hi": "लूप आखिरी संख्या के बाद एक और संख्या ढूँढता है। वह होती नहीं, इसलिए सूची खत्म होते ही प्रोग्राम रुक जाता है।",
        "description": "A loop over range(len(items)) also indexes items[i + 1].",
    },
    "off_by_one_skip_first": {
        "title": "Loop starts at 1 and skips the first item",
        "category": "logic",
        "severity": "medium",
        "confidence": 0.74,
        "always_review": True,
        "impact": "The first record is missing from the total. A one-item list totals to zero.",
        "root_cause": "The loop starts at index 1, so index 0 is never added. The total is short by whatever was stored in the first row.",
        "trigger": "Pass a list whose first quantity is not zero. Compare the total with a hand calculation.",
        "student": "The program starts counting from the second row. The first row is left out, so the total is too small.",
        "kn": "ಪ್ರೋಗ್ರಾಂ ಎರಡನೇ ಸಾಲಿನಿಂದ ಎಣಿಕೆ ಶುರು ಮಾಡುತ್ತದೆ. ಮೊದಲ ಸಾಲು ಬಿಟ್ಟುಹೋಗುತ್ತದೆ, ಒಟ್ಟು ಕಡಿಮೆಯಾಗುತ್ತದೆ.",
        "hi": "प्रोग्राम गिनती दूसरी पंक्ति से शुरू करता है। पहली पंक्ति छूट जाती है, इसलिए कुल कम आता है।",
        "description": "range(1, len(items)) skips the item at index 0 while totalling the list.",
    },
}


def text_for(rule_id: str) -> dict:
    spec = CATALOG.get(rule_id)
    if spec is None:
        return {
            "title": rule_id.replace("_", " "),
            "category": "quality",
            "severity": "low",
            "confidence": 0.55,
            "impact": "Worth a look, but this came from a general linter and may not change behaviour.",
            "root_cause": "A static tool reported this pattern.",
            "trigger": "Open the file at the reported line.",
            "student": "A checker noticed something on this line. Ask someone to confirm it is a real bug.",
            "kn": "ಪರೀಕ್ಷಕ ಈ ಸಾಲಿನಲ್ಲಿ ಏನೋ ಗಮನಿಸಿದೆ. ಅದು ನಿಜವಾದ ದೋಷವೇ ಎಂದು ಯಾರಾದರೂ ಖಚಿತಪಡಿಸಬೇಕು.",
            "hi": "एक जाँचने वाले ने इस पंक्ति पर कुछ देखा है। कोई पुष्टि करे कि यह सच में गलती है।",
            "description": rule_id,
            "always_review": True,
        }
    return spec


def needs_review(confidence: float, rule_id: str) -> bool:
    spec = CATALOG.get(rule_id, {})
    if spec.get("always_review"):
        return True
    return confidence < REVIEW_BELOW
