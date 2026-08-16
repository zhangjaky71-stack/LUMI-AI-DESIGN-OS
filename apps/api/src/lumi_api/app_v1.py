from lumi_api.api import create_contract_app
from lumi_api.billing_http import install_stripe_billing

app = create_contract_app()
install_stripe_billing(app)
