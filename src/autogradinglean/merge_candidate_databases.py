import pandas as pd

def merge_student_data(classroom_roster, sits_candidate_file):
    """Merges candidate data from a GitHub Classroom classroom roster CSV file and a XLSX file
    extracted from SITS.
    
    The SITS data should contain the following columns:

        'student number', 'candidate number', 'first name', 'last name', 'email'.

    The 'candidate number' is expected to be a string of 6 digits, padded left with zeros.

    The columns of the classroom roster should be:

        'identifier', 'github_username', 'github_id', 'name'

    The 'identifier' should correspond with the 'candidate number' from the SITS spreadsheet.
    """
    # Read the GitHub Classroom roster CSV into a DataFrame
    df_classroom_roster = pd.read_csv(classroom_roster, dtype=object)

    sits_candidate_columns= ['student number', 'candidate number', 'first name', 'last name', 'email']
    # Read the University student records Excel spreadsheet into a DataFrame
    df_sits_candidates = pd.read_excel(sits_candidate_file, header=None, names=sits_candidate_columns, dtype=object)
    # Convert the 'candidate number' to string, ensuring it's 6 digits and zero-padded
    df_sits_candidates['candidate number'] = df_sits_candidates['candidate number'].astype(int).astype(str).apply(lambda x: x.zfill(6))

    # Merge the two DataFrames based on 'identifier' and 'candidate number'
    df_merged = pd.merge(df_classroom_roster, df_sits_candidates, left_on='identifier', right_on='candidate number', how='outer')

    # Handle discrepancies between the classroom_roster and the sits_candidate_file
    # In particular, find those rows where there is either no classroom roster identifier
    # or no sits candidate number
    #df_merged['discrepancy'] = df_merged.apply(lambda row: pd.isna(row['identifier']) or pd.isna(row['candidate number']), axis=1)

    # Save the merged DataFrame to a new CSV file
    return(df_merged)
    #df_merged.to_csv(output_csv_path, index=False)

# Example usage
# merge_student_data('github_classroom_roster.csv', 'university_records.csv', 'merged_student_data.csv')
