def apply_discount(price, discount_percent):
    # bug: forgot to divide discount_percent by 100
    return price - (price * discount_percent / 100)

