Feature: ERISA Restriction and Prohibited Transaction Detection
  As an ERISA compliance analyst
  I want the system to detect when a securitisation instrument has ERISA restrictions
  or triggers prohibited transactions under ERISA §406(a)
  So that benefit plan investors are protected from fiduciary violations

  Background:
    Given the knowledge graph is initialised with FIBO schema
    And the rule registry is loaded with "eu_sec_v2.yaml"

  Scenario: Instrument with ERISA restriction is flagged
    Given a CLO instrument with ISIN "EU-CLO-2024-01"
    And the instrument has an ERISA restriction recorded
    When rule "ERISA_SECTION_3" is evaluated against the instrument
    Then the verdict is "non_compliant"
    And the result includes "benefit plan investor" in the explanation
    And the result flags human review required

  Scenario: Instrument with valid QPAM exemption passes restriction check
    Given a CLO instrument with ISIN "EU-CLO-2024-QPAM"
    And the instrument has an ERISA restriction recorded
    And the instrument has a QPAM exemption certificate with status "valid"
    When rule "ERISA_QPAM" is evaluated against the instrument
    Then the verdict is "compliant"
    And the confidence score is greater than 0.85

  Scenario: Instrument without ERISA restriction has no prohibited transaction
    Given an ABS instrument with ISIN "EU-ABS-2024-02"
    And the instrument has no ERISA restriction recorded
    When rule "ERISA_406A" is evaluated against the instrument
    Then the verdict is "compliant"

  Scenario: Instrument with expired QPAM exemption triggers non-compliance
    Given a CLO instrument with ISIN "EU-CLO-2024-EXPIRED"
    And the instrument has an ERISA restriction recorded
    And the instrument has a QPAM exemption certificate with status "expired"
    When rule "ERISA_QPAM" is evaluated against the instrument
    Then the verdict is "non_compliant"
    And the result flags human review required
