import pandas as pd

data = {
    "record_id": [1, 2, 3],
    "object_type": ["A", "B", "C"],
    "values": [
        ["alpha", "beta", "gamma"],  # list of strings
        [],                          # empty list
        ["cat", "dog"]               # list of strings
    ]
}

df = pd.DataFrame(data)
print(df)
# Explode the 'values' column
df_exploded = df.explode("values")

print(df_exploded)

all_data = pd.concat([df_exploded,pd.DataFrame([])], ignore_index=True)

print(all_data)