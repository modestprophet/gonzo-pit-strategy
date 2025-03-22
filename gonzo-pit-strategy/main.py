from security import get_database_url

def main():
    db_url = get_database_url()

    #TODO: don't print the full db_url with secrets to stdout, lol
    print(db_url)


if __name__ == "__main__":
    main()
