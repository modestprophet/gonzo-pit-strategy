from db.repositiries.data_repository import F1DataRepository

def main():
    df = F1DataRepository.get_all_race_history()
    df.to_csv('output.csv', index=False, header=True, sep=';', na_rep='NA', encoding='utf-8')


if __name__ == "__main__":
    main()
