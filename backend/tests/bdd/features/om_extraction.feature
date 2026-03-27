Feature: Offering Memorandum Economic Terms and Key Party Extraction
  As a legal analyst
  I want the system to verify that an Offering Memorandum contains all required
  economic terms and key party disclosures
  So that I can confirm the document meets Prospectus Regulation requirements

  Background:
    Given the knowledge graph is initialised with FIBO schema
    And the rule registry is loaded with "eu_sec_v2.yaml"

  Scenario: OM with all required economic terms passes
    Given a document of type "OfferingMemorandum" with ID "OM-CLO-2024-01"
    And the document discloses coupon rate "4.5%"
    And the document discloses maturity date "2034-07-15"
    And the document discloses management fee "0.40%"
    When rule "OM_ECONOMIC_TERMS" is evaluated against the document
    Then the verdict is "compliant"
    And the confidence score is greater than 0.80

  Scenario: OM missing maturity date is non-compliant
    Given a document of type "OfferingMemorandum" with ID "OM-INCOMPLETE-01"
    And the document discloses coupon rate "5.0%"
    And the document has no maturity date
    When rule "OM_ECONOMIC_TERMS" is evaluated against the document
    Then the verdict is "non_compliant"
    And the explanation mentions "maturity"

  Scenario: OM identifying all key parties passes
    Given a document of type "OfferingMemorandum" with ID "OM-CLO-2024-01"
    And the document identifies manager "GreenField Capital Advisors"
    And the document identifies trustee "North Trust Bank"
    And the document identifies servicer "SecureServ LLC"
    When rule "OM_KEY_PARTIES" is evaluated against the document
    Then the verdict is "compliant"

  Scenario: OM with missing trustee identification is non-compliant
    Given a document of type "OfferingMemorandum" with ID "OM-MISSING-TRUSTEE"
    And the document identifies manager "GreenField Capital Advisors"
    And the document has no trustee identified
    When rule "OM_KEY_PARTIES" is evaluated against the document
    Then the verdict is "non_compliant"
    And the explanation mentions "trustee"
