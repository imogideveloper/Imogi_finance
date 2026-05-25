"""Formula tunjangan: nilai SSA = nominal bulanan (bukan per hari)."""

# Nilai di SSA / meal_allowance / transport_allowance = per bulan.
# Prorate jika payment_days < total_working_days.
MEAL_ALLOWANCE_FORMULA = (
	"(meal_allowance / total_working_days) * payment_days "
	"if total_working_days else meal_allowance"
)
TRANSPORT_ALLOWANCE_FORMULA = (
	"(transport_allowance / total_working_days) * payment_days "
	"if total_working_days else transport_allowance"
)
OPERATIONAL_ALLOWANCE_FORMULA = (
	"(tunjangan_operational / total_working_days) * payment_days "
	"if total_working_days else tunjangan_operational"
)

LEGACY_FORMULAS = {
	"Tunjangan Makan": (
		"payment_days * meal_allowance",
		MEAL_ALLOWANCE_FORMULA,
	),
	"Tunjangan Transport": (
		"payment_days * transport_allowance",
		TRANSPORT_ALLOWANCE_FORMULA,
	),
}
