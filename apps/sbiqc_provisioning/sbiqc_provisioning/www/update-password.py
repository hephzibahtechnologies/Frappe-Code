# Visual-only override of the set/reset password page (see www/update-password.html in this app).
# Frappe pairs a www template with a same-named .py in the *same* app/folder
# for its context -- reuse the core logic unchanged instead of duplicating it.
from frappe.www.update_password import get_context  # noqa: F401

# `set_pymodule_properties` reads module-level attrs like this one directly
# off *this* module, not the one get_context came from -- must be repeated.
no_cache = 1
