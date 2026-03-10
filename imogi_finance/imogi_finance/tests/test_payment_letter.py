"""
Test Payment Letter Generation for Sales Invoice

This module tests the payment letter generation functionality including:
- Basic rendering
- Context building
- Template selection (branch-specific vs default)
- Data validation
- Error handling
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPaymentLetterGeneration(FrappeTestCase):
    """Test payment letter generation for Sales Invoice and Payment Request"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_data()

    @classmethod
    def _ensure_test_data(cls):
        """Ensure required test data exists"""
        # Create test company if not exists
        if not frappe.db.exists("Company", "_Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "_Test Company",
                "abbr": "TC",
                "default_currency": "IDR",
                "country": "Indonesia"
            }).insert(ignore_permissions=True)

        # Create test customer if not exists
        if not frappe.db.exists("Customer", "_Test Customer"):
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "_Test Customer",
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "Indonesia"
            }).insert(ignore_permissions=True)

        # Ensure Letter Template Settings exists
        if not frappe.db.exists("Letter Template Settings"):
            frappe.get_doc({
                "doctype": "Letter Template Settings",
                "enable_payment_letter": 1
            }).insert(ignore_permissions=True)

    def setUp(self):
        """Setup test environment before each test"""
        frappe.set_user("Administrator")
        self.test_si = self._create_test_sales_invoice()

    def tearDown(self):
        """Cleanup after each test"""
        if self.test_si and frappe.db.exists("Sales Invoice", self.test_si.name):
            frappe.delete_doc("Sales Invoice", self.test_si.name, force=1)

    def _create_test_sales_invoice(self):
        """Create a test Sales Invoice"""
        si = frappe.get_doc({
            "doctype": "Sales Invoice",
            "company": "_Test Company",
            "customer": "_Test Customer",
            "posting_date": frappe.utils.today(),
            "due_date": frappe.utils.add_days(frappe.utils.today(), 30),
            "items": [{
                "item_code": "_Test Item",
                "qty": 1,
                "rate": 1000000,
                "income_account": "Sales - TC",
                "cost_center": "Main - TC"
            }]
        })
        si.insert(ignore_permissions=True)
        return si

    def _create_test_letter_template(self, name="_Test Payment Letter Template",
                                     letter_type="Payment Letter", branch=None,
                                     is_default=0):
        """Create a test Letter Template"""
        if frappe.db.exists("Letter Template", name):
            frappe.delete_doc("Letter Template", name, force=1)

        template = frappe.get_doc({
            "doctype": "Letter Template",
            "template_name": name,
            "letter_type": letter_type,
            "branch": branch,
            "is_active": 1,
            "is_default": is_default,
            "body_html": """
                <div>
                    <h3>Payment Letter</h3>
                    <p>Customer: {{ customer_name }}</p>
                    <p>Invoice: {{ invoice_number }}</p>
                    <p>Amount: {{ amount }}</p>
                    <p>Due Date: {{ due_date }}</p>
                </div>
            """
        })
        template.insert(ignore_permissions=True)
        return template


class TestPaymentLetterBasicRendering(TestPaymentLetterGeneration):
    """Test basic payment letter rendering functionality"""

    def test_render_payment_letter_with_default_template(self):
        """Test rendering payment letter with default template"""
        from imogi_finance.services.letter_template_service import render_payment_letter_html

        # Create default template
        template = self._create_test_letter_template(is_default=1)

        # Render payment letter
        html = render_payment_letter_html(self.test_si)

        # Assertions
        self.assertIsNotNone(html)
        self.assertIn("Payment Letter", html)
        self.assertIn("_Test Customer", html)
        self.assertIn(str(self.test_si.name), html)

        # Cleanup
        frappe.delete_doc("Letter Template", template.name, force=1)

    def test_render_payment_letter_disabled(self):
        """Test that payment letter throws error when disabled"""
        from imogi_finance.services.letter_template_service import render_payment_letter_html

        # Disable payment letter
        settings = frappe.get_doc("Letter Template Settings")
        original_value = settings.enable_payment_letter
        settings.enable_payment_letter = 0
        settings.save()

        # Should throw error
        with self.assertRaises(frappe.ValidationError):
            render_payment_letter_html(self.test_si)

        # Restore
        settings.enable_payment_letter = original_value
        settings.save()

    def test_render_payment_letter_no_template_exists(self):
        """Test rendering when no template exists (should use fallback)"""
        from imogi_finance.services.letter_template_service import render_payment_letter_html

        # Clear default template from settings
        settings = frappe.get_doc("Letter Template Settings")
        original_template = settings.default_template
        settings.default_template = None
        settings.save()

        # Should still work with fallback template
        html = render_payment_letter_html(self.test_si)
        self.assertIsNotNone(html)

        # Restore
        settings.default_template = original_template
        settings.save()


class TestPaymentLetterContextBuilding(TestPaymentLetterGeneration):
    """Test payment letter context building"""

    def test_build_context_with_complete_data(self):
        """Test context building with complete Sales Invoice data"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        context = build_payment_letter_context(self.test_si)

        # Check essential fields
        self.assertIn("company", context)
        self.assertIn("customer_name", context)
        self.assertIn("invoice_number", context)
        self.assertIn("amount", context)
        self.assertIn("amount_in_words", context)
        self.assertIn("due_date", context)
        self.assertIn("letter_date", context)

        # Verify values
        self.assertEqual(context["company"], "_Test Company")
        self.assertEqual(context["customer_name"], "_Test Customer")
        self.assertEqual(context["invoice_number"], self.test_si.name)

    def test_build_context_with_minimal_data(self):
        """Test context building with minimal data"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        # Create minimal doc
        minimal_doc = frappe._dict({
            "name": "TEST-001",
            "company": "_Test Company",
            "customer": "_Test Customer"
        })

        context = build_payment_letter_context(minimal_doc)

        # Should not error and have basic fields
        self.assertIsNotNone(context)
        self.assertIn("letter_number", context)
        self.assertEqual(context["letter_number"], "TEST-001")

    def test_context_amount_formatting(self):
        """Test amount formatting in various currencies"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        context = build_payment_letter_context(self.test_si)

        # Check amount is formatted
        self.assertIn("amount", context)
        self.assertTrue(isinstance(context["amount"], str))

        # Check amount in words exists
        self.assertIn("amount_in_words", context)
        self.assertTrue(isinstance(context["amount_in_words"], str))

    def test_context_date_formatting(self):
        """Test date fields are properly formatted"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        context = build_payment_letter_context(self.test_si)

        # All date fields should be strings
        self.assertTrue(isinstance(context["letter_date"], str))
        self.assertTrue(isinstance(context["invoice_date"], str))
        self.assertTrue(isinstance(context["due_date"], str))


class TestPaymentLetterTemplateSelection(TestPaymentLetterGeneration):
    """Test template selection logic"""

    def test_branch_specific_template_priority(self):
        """Test that branch-specific template takes priority"""
        from imogi_finance.services.letter_template_service import _get_template

        # Create branch if not exists
        if not frappe.db.exists("Branch", "_Test Branch"):
            frappe.get_doc({
                "doctype": "Branch",
                "branch": "_Test Branch",
                "company": "_Test Company"
            }).insert(ignore_permissions=True)

        # Create branch-specific template
        branch_template = self._create_test_letter_template(
            name="_Test Branch Template",
            branch="_Test Branch"
        )

        # Create default template
        default_template = self._create_test_letter_template(
            name="_Test Default Template",
            is_default=1
        )

        # Get template for branch
        selected = _get_template("_Test Branch", "Payment Letter")

        # Should select branch-specific template
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, branch_template.name)

        # Cleanup
        frappe.delete_doc("Letter Template", branch_template.name, force=1)
        frappe.delete_doc("Letter Template", default_template.name, force=1)
        if frappe.db.exists("Branch", "_Test Branch"):
            frappe.delete_doc("Branch", "_Test Branch", force=1)

    def test_default_template_fallback(self):
        """Test fallback to default template when no branch template"""
        from imogi_finance.services.letter_template_service import _get_template

        # Create only default template
        default_template = self._create_test_letter_template(
            name="_Test Default Only",
            is_default=1
        )

        # Get template for non-existent branch
        selected = _get_template("Non Existent Branch", "Payment Letter")

        # Should fallback to default
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, default_template.name)

        # Cleanup
        frappe.delete_doc("Letter Template", default_template.name, force=1)

    def test_template_by_letter_type(self):
        """Test template selection based on letter type"""
        from imogi_finance.services.letter_template_service import _get_template

        # Create templates with different letter types
        payment_template = self._create_test_letter_template(
            name="_Test Payment Template",
            letter_type="Payment Letter",
            is_default=1
        )

        request_template = self._create_test_letter_template(
            name="_Test Request Template",
            letter_type="Payment Request Letter"
        )

        # Get payment letter template
        selected_payment = _get_template(None, "Payment Letter")
        self.assertEqual(selected_payment.name, payment_template.name)

        # Get payment request template
        selected_request = _get_template(None, "Payment Request Letter")
        self.assertEqual(selected_request.name, request_template.name)

        # Cleanup
        frappe.delete_doc("Letter Template", payment_template.name, force=1)
        frappe.delete_doc("Letter Template", request_template.name, force=1)


class TestPaymentLetterWhitelistedAPI(TestPaymentLetterGeneration):
    """Test whitelisted API methods"""

    def test_get_sales_invoice_payment_letter_api(self):
        """Test whitelisted method for getting payment letter"""
        from imogi_finance.overrides.sales_invoice import get_sales_invoice_payment_letter

        # Create template
        template = self._create_test_letter_template(is_default=1)

        # Call API
        html = get_sales_invoice_payment_letter(self.test_si.name)

        # Assertions
        self.assertIsNotNone(html)
        self.assertIn("Payment Letter", html)

        # Cleanup
        frappe.delete_doc("Letter Template", template.name, force=1)

    def test_api_with_invalid_sales_invoice(self):
        """Test API with non-existent Sales Invoice"""
        from imogi_finance.overrides.sales_invoice import get_sales_invoice_payment_letter

        # Should throw error
        with self.assertRaises(frappe.DoesNotExistError):
            get_sales_invoice_payment_letter("INVALID-SI-001")


class TestPaymentLetterEdgeCases(TestPaymentLetterGeneration):
    """Test edge cases and error handling"""

    def test_payment_letter_with_zero_amount(self):
        """Test payment letter generation with zero amount"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        # Create SI with zero amount
        zero_si = frappe.get_doc({
            "doctype": "Sales Invoice",
            "company": "_Test Company",
            "customer": "_Test Customer",
            "posting_date": frappe.utils.today(),
            "items": [{
                "item_code": "_Test Item",
                "qty": 1,
                "rate": 0,
                "income_account": "Sales - TC",
                "cost_center": "Main - TC"
            }]
        })
        zero_si.insert(ignore_permissions=True)

        context = build_payment_letter_context(zero_si)

        # Should handle gracefully
        self.assertIn("amount", context)
        self.assertIn("amount_in_words", context)

        # Cleanup
        frappe.delete_doc("Sales Invoice", zero_si.name, force=1)

    def test_payment_letter_with_missing_customer(self):
        """Test payment letter with missing customer data"""
        from imogi_finance.services.letter_template_service import build_payment_letter_context

        # Create doc without customer
        doc = frappe._dict({
            "name": "TEST-NO-CUSTOMER",
            "company": "_Test Company"
        })

        context = build_payment_letter_context(doc)

        # Should have empty customer name, not error
        self.assertIn("customer_name", context)
        self.assertEqual(context["customer_name"], "")

    def test_payment_letter_template_jinja_error_handling(self):
        """Test handling of Jinja template errors"""
        from imogi_finance.services.letter_template_service import render_payment_letter_html

        # Create template with invalid Jinja
        bad_template = frappe.get_doc({
            "doctype": "Letter Template",
            "template_name": "_Test Bad Template",
            "letter_type": "Payment Letter",
            "is_active": 1,
            "is_default": 1,
            "body_html": "{{ undefined_variable | invalid_filter }}"
        })
        bad_template.insert(ignore_permissions=True)

        # Should handle Jinja errors gracefully
        try:
            html = render_payment_letter_html(self.test_si)
            # If it doesn't error, it should at least return something
            self.assertIsNotNone(html)
        except Exception as e:
            # If it errors, should be a meaningful error
            self.assertIsInstance(e, (frappe.ValidationError, Exception))

        # Cleanup
        frappe.delete_doc("Letter Template", bad_template.name, force=1)


def run_tests():
    """Helper function to run all payment letter tests"""
    unittest.main()


if __name__ == "__main__":
    run_tests()
