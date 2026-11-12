# Eval Results

**10/11 passed**

| ID | Question | Answerable | Pass | Latency | Notes |
|---|---|---|---|---|---|
| 1 | What is the recommended coolant concentration for the TX-200 | True | PASS | 2561ms |  |
| 2 | The machine is showing alarm AL-104. What does it mean and w | True | PASS | 1658ms |  |
| 3 | Who is allowed to remove a lockout lock from a machine? | True | PASS | 1796ms |  |
| 4 | What is the outer diameter tolerance for the BH-220 bearing  | True | PASS | 1980ms |  |
| 5 | How often should spindle runout be checked, and who does it? | True | FAIL | 1203ms | missing fact: '0.005' |
| 6 | How many samples do I inspect for a lot of 200 pieces? | True | PASS | 1642ms |  |
| 7 | Where do I put rejected material? | True | PASS | 22618ms |  |
| 8 | What should I do before replacing a hydraulic hose on the TX | True | PASS | 2033ms |  |
| 9 | A lot arrived without a Material Test Certificate. Can I ins | True | PASS | 2308ms |  |
| 10 | What is the maximum spindle speed of the TX-200? | False | PASS | 2072ms |  |
| 11 | What does alarm AL-999 mean? | False | PASS | 1343ms |  |

## Answers

### Q1: What is the recommended coolant concentration for the TX-200 CNC turning centre?

**Answerable:** True  
**Answer:** 6 - 8 %

**Sources:**
- MNT-MAN-CNC-02 Rev 02 p.1 s.3 Operating Parameters

### Q2: The machine is showing alarm AL-104. What does it mean and what should the operator do?

**Answerable:** True  
**Answer:** AL-104 means Way lube oil level low. Operator action: Top up with ISO VG 68 oil to the MAX mark, then press RESET. Machine can continue after reset.

**Sources:**
- MNT-MAN-CNC-02 Rev 02 p.2 s.6 Common Alarms

### Q3: Who is allowed to remove a lockout lock from a machine?

**Answerable:** True  
**Answer:** Only the owner (the authorised person who applied the lock) is allowed to remove their own lock. If the owner is absent, the lock may be removed only through the specific procedure involving Production Manager and Safety Officer authorisation and the SF-12 form. Follow the SOP.

**Sources:**
- SAF-SOP-003 Rev 05 p.1 s.6 Removal of a Lock When the Owner Is Absent
- SAF-SOP-003 Rev 05 p.1 s.3 Definitions

### Q4: What is the outer diameter tolerance for the BH-220 bearing housing?

**Answerable:** True  
**Answer:** 90.000 mm +/- 0.050 mm

**Sources:**
- QC-SOP-014 Rev 04 p.2 s.6 Inspection Dimensions - BH-220 Bearing Housing (Machined, from

### Q5: How often should spindle runout be checked, and who does it?

**Answerable:** True  
**Answer:** Spindle runout should be checked monthly by the Maintenance technician.

**Sources:**
- MNT-MAN-CNC-02 Rev 02 p.1 s.4 Preventive Maintenance Schedule

### Q6: How many samples do I inspect for a lot of 200 pieces?

**Answerable:** True  
**Answer:** 13

**Superseded note:** Note: An older revision (QC-SOP-014 Rev 03) also matched. Rev 04, effective 01-Jul-2026, is the current version and supersedes it.

**Sources:**
- QC-SOP-014 Rev 04 p.1 s.4 Sampling Plan

### Q7: Where do I put rejected material?

**Answerable:** True  
**Answer:** Tag with a RED tag and move to Quarantine Cage Q1, Stores Bay 3.

**Sources:**
- QC-SOP-014 Rev 04 p.2 s.8

### Q8: What should I do before replacing a hydraulic hose on the TX-200?

**Answerable:** True  
**Answer:** Isolate the machine as per SAF-SOP-003 Lockout/Tagout. Never open the hydraulic circuit on a running or energised machine. Follow the SOP.

**Sources:**
- MNT-MAN-CNC-02 Rev 02 p.1 s.2 Safety First

### Q9: A lot arrived without a Material Test Certificate. Can I inspect it?

**Answerable:** True  
**Answer:** No. The lot is put on HOLD and must not be inspected or accepted until the MTC is received.

**Superseded note:** Note: An older revision (QC-SOP-014 Rev 03) also matched. Rev 04, effective 01-Jul-2026, is the current version and supersedes it.

**Sources:**
- QC-SOP-014 Rev 04 p.2 s.2

### Q10: What is the maximum spindle speed of the TX-200?

**Answerable:** False  
**Answer:** 


### Q11: What does alarm AL-999 mean?

**Answerable:** False  
**Answer:** 


