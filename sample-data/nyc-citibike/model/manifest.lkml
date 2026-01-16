project_name: "nyc_citibike_trips"

constant: CONNECTION_NAME {
  value: "default_bigquery_connection"
  export: override_optional
}

constant: DATASET_NAME {
  value: "bigquery-public-data.new_york"
  export: override_optional
}
