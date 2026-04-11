from dotenv import dotenv_values
d = dotenv_values(".env")
print(f"FIRAC: '{d.get('FIRAC_FORMAT_STYLE')}'")
print(f"ELIGIBLE: '{d.get('ENABLE_ELIGIBILITY_CHECK')}'")
