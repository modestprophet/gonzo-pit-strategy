from security import get_database_credentials

def main():
    db_url = get_database_credentials()

    #TODO: don't print the full db_url with secrets to stdout, lol
    print(db_url)


if __name__ == "__main__":
    main()
