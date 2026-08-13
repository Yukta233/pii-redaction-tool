"""
Synthetic labeled test set for evaluating the redactor.

The real prospectus (Red_Herring_Prospectus.docx) contains names, company
names, addresses, emails and phone numbers -- but essentially no SSNs,
credit card numbers, or IP addresses (these categories don't naturally
occur in an IPO filing). To measure recall/precision honestly across ALL
9 required PII types, we use a synthetic "support ticket log" style
document (matching the style shown in the assignment example) with a
hand-built ground truth list.

Each ground-truth entry is (pii_type, exact_substring_as_it_appears_in_text).
"""

TEST_DOCUMENT = """
Ticket #4521 - Account Access Issue
Submitted by: Rashi Patil
Email: rashi.patil@gmail.com
Phone: +91 9876543210
Company: BlueOrbit Technologies Pvt Ltd
Message: Hi team, I'm unable to log into my account. My date of birth on
file is 14/03/1990 for verification. I was connecting from IP 192.168.1.42
when the error occurred. Please reach me at rashi.patil@gmail.com if you
need more details.

Ticket #4522 - Billing Dispute
Submitted by: Rohan Dey
Email: rohan.dey@gmail.com
Phone: +91 9123456780
Company: Nimbus Retail Solutions
Message: I was charged twice on my card ending in the number
4539 1488 0343 6467. My SSN for identity verification is 123-45-6789.
I live at 221B Baker Street, London. Please refund the extra charge.
Contact me anytime at rohan.dey@gmail.com or +91 9123456780.

Ticket #4523 - Delivery Delay
Submitted by: Ananya Sharma
Email: ananya.sharma@outlook.com
Phone: +91 9988776655
Company: Waterloo Industrial Park VI Private Limited
Message: My order hasn't arrived. Date of Birth: 22-11-1985. I connected
from IP address 10.0.0.15 to check my order status. My mailing address is
45 Sarthak Nagar, Baner, Pune - 411045, Maharashtra, India.

Ticket #4524 - Refund Request
Submitted by: Karan Malhotra
Email: karan.malhotra@yahoo.com
Phone: +91 9012345678
Company: KSH International Limited
Message: Please process my refund to the card 5105 1051 0510 5100.
My SSN is 987-65-4321. Reach me at karan.malhotra@yahoo.com.
"""

# (pii_type, exact substring). Order-independent; duplicates of the same
# value are allowed since the same PII can legitimately repeat.
GROUND_TRUTH = [
    ("NAME", "Rashi Patil"),
    ("EMAIL", "rashi.patil@gmail.com"),
    ("PHONE", "+91 9876543210"),
    ("COMPANY", "BlueOrbit Technologies Pvt Ltd"),
    ("DOB", "14/03/1990"),
    ("IP_ADDRESS", "192.168.1.42"),
    ("EMAIL", "rashi.patil@gmail.com"),  # 2nd occurrence

    ("NAME", "Rohan Dey"),
    ("EMAIL", "rohan.dey@gmail.com"),
    ("PHONE", "+91 9123456780"),
    ("COMPANY", "Nimbus Retail Solutions"),
    ("CREDIT_CARD", "4539 1488 0343 6467"),
    ("SSN", "123-45-6789"),
    ("ADDRESS", "221B Baker Street, London"),
    ("EMAIL", "rohan.dey@gmail.com"),  # 2nd occurrence
    ("PHONE", "+91 9123456780"),  # 2nd occurrence

    ("NAME", "Ananya Sharma"),
    ("EMAIL", "ananya.sharma@outlook.com"),
    ("PHONE", "+91 9988776655"),
    ("COMPANY", "Waterloo Industrial Park VI Private Limited"),
    ("DOB", "22-11-1985"),
    ("IP_ADDRESS", "10.0.0.15"),
    ("ADDRESS", "45 Sarthak Nagar, Baner, Pune - 411045, Maharashtra, India"),

    ("NAME", "Karan Malhotra"),
    ("EMAIL", "karan.malhotra@yahoo.com"),
    ("PHONE", "+91 9012345678"),
    ("COMPANY", "KSH International Limited"),
    ("CREDIT_CARD", "5105 1051 0510 5100"),
    ("SSN", "987-65-4321"),
    ("EMAIL", "karan.malhotra@yahoo.com"),  # 2nd occurrence
]
