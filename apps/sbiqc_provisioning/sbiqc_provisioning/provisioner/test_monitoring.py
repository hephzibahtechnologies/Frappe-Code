# Copyright (c) 2026, SBIQC and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from sbiqc_provisioning.provisioner import monitoring


class IntegrationTestMonitoring(IntegrationTestCase):
	def tearDown(self):
		frappe.db.delete("Error Log", {"method": monitoring.HEALTH_CHECK_ERROR_TITLE})
		frappe.db.commit()
		super().tearDown()

	def test_healthy_result_logs_nothing(self):
		with patch.object(monitoring, "get_bench_health", return_value={"overall": "ok", "checks": []}):
			monitoring.check_bench_health()
		self.assertFalse(frappe.db.exists("Error Log", {"method": monitoring.HEALTH_CHECK_ERROR_TITLE}))

	def test_unhealthy_result_logs_error(self):
		bad_result = {
			"overall": "error",
			"checks": [
				{"name": "MariaDB", "status": "ok"},
				{"name": "Redis Cache", "status": "error", "detail": "connection refused"},
			],
		}
		with patch.object(monitoring, "get_bench_health", return_value=bad_result):
			monitoring.check_bench_health()

		log = frappe.get_all(
			"Error Log", filters={"method": monitoring.HEALTH_CHECK_ERROR_TITLE}, fields=["error"]
		)
		self.assertEqual(len(log), 1)
		self.assertIn("Redis Cache", log[0].error)
		self.assertIn("connection refused", log[0].error)

	def test_repeated_unhealthy_results_are_deduplicated(self):
		bad_result = {"overall": "error", "checks": [{"name": "MariaDB", "status": "error"}]}
		with patch.object(monitoring, "get_bench_health", return_value=bad_result):
			monitoring.check_bench_health()
			monitoring.check_bench_health()
			monitoring.check_bench_health()

		count = frappe.db.count("Error Log", {"method": monitoring.HEALTH_CHECK_ERROR_TITLE})
		self.assertEqual(count, 1)

	def test_get_bench_health_exception_is_caught_not_raised(self):
		with patch.object(monitoring, "get_bench_health", side_effect=RuntimeError("boom")):
			monitoring.check_bench_health()  # must not raise

		log = frappe.get_all(
			"Error Log", filters={"method": monitoring.HEALTH_CHECK_ERROR_TITLE}, fields=["error"]
		)
		self.assertEqual(len(log), 1)
		self.assertIn("boom", log[0].error)
