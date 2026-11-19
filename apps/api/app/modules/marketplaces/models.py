"""Schema objects shared by the imported-product shops: the order-number
sequence.

It lives here rather than in one shop because the customer's "My orders"
lists AliExpress, CJ and Shopify orders together, so numbers must be unique
across all of them. Placing it in one shop's module would force the others to
import it, breaking the isolation described in `marketplaces/rules.py`.

The database assigns the number (`server_default=nextval`): a Postgres
sequence never duplicates, even with concurrent inserts from different
processes.
"""

from sqlalchemy import Sequence

from app.foundation.db import Base

#: Starts at 1000 so low order numbers do not reveal total order volume.
SHOP_ORDER_NUMBER_START = 1000

SHOP_ORDER_NUMBER_SEQ = Sequence(
    "sn_order_number_seq", start=SHOP_ORDER_NUMBER_START, metadata=Base.metadata
)
