Feature: EU Securitisation Risk Retention Compliance
  As a compliance officer
  I want the system to detect when a securitisation instrument does not meet the
  5% net economic interest retention requirement under EUSR Art 6(1)
  So that I can take remediation action before investing or reporting

  Background:
    Given the knowledge graph is initialised with FIBO schema
    And the rule registry is loaded with "eu_sec_v2.yaml"

  Scenario: Compliant instrument with 5% retention passes
    Given a CLO instrument with ISIN "EU-CLO-2024-01"
    And the instrument has a retention percentage of 5.0
    And the retained interest is held by the originator
    When rule "RISK_RETENTION" is evaluated against the instrument
    Then the verdict is "compliant"
    And the confidence score is greater than 0.85
    And the result includes evidence citing the retention figure

  Scenario: Non-compliant instrument with only 3% retention fails
    Given a CLO instrument with ISIN "EU-CLO-2024-04"
    And the instrument has a retention percentage of 3.0
    When rule "RISK_RETENTION" is evaluated against the instrument
    Then the verdict is "non_compliant"
    And the result flags human review required
    And the explanation mentions "Article 6" and "5%"

  Scenario: Instrument without retention data triggers insufficient evidence
    Given an ABS instrument with ISIN "EU-ABS-UNKNOWN-01"
    And the instrument has no retention data recorded
    When rule "RISK_RETENTION" is evaluated against the instrument
    Then the verdict is "insufficient_evidence"
    And the result flags human review required

  Scenario: STS designated instrument also passes transparency check
    Given a RMBS instrument with ISIN "EU-RMBS-2024-03"
    And the instrument has STS designation "true"
    And the instrument has a quarterly investor report published
    When rule "TRANSPARENCY" is evaluated against the instrument
    Then the verdict is "compliant"
    And the confidence score is greater than 0.80
