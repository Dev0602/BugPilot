def get_user_email(user_dict):
    # bug: assumes key always exists
    return user_dict.get("email")

