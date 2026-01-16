view: trips {
  sql_table_name: `@{DATASET_NAME}.citibike_trips` ;;

  dimension_group: start {
    type: time
    timeframes: [raw, time, date, week, month, year, hour_of_day, day_of_week, day_of_year]
    sql: ${TABLE}.starttime ;;
  }

  dimension_group: stop {
    type: time
    timeframes: [raw, time, date, week, month, year]
    sql: ${TABLE}.stoptime ;;
  }

  dimension: trip_duration {
    type: number
    sql: ${TABLE}.tripduration ;;
    label: "Trip Duration (Seconds)"
  }

  dimension: start_station_id {
    type: string
    sql: CAST(${TABLE}.start_station_id AS STRING) ;;
  }

  dimension: start_station_name {
    type: string
    sql: ${TABLE}.start_station_name ;;
  }

  dimension: start_station_latitude {
    type: number
    sql: ${TABLE}.start_station_latitude ;;
  }

  dimension: start_station_longitude {
    type: number
    sql: ${TABLE}.start_station_longitude ;;
  }

  dimension: start_station_location {
    type: location
    sql_latitude: ${start_station_latitude} ;;
    sql_longitude: ${start_station_longitude} ;;
  }

  dimension: end_station_id {
    type: string
    sql: CAST(${TABLE}.end_station_id AS STRING) ;;
  }

  dimension: end_station_name {
    type: string
    sql: ${TABLE}.end_station_name ;;
  }

  dimension: end_station_latitude {
    type: number
    sql: ${TABLE}.end_station_latitude ;;
  }

  dimension: end_station_longitude {
    type: number
    sql: ${TABLE}.end_station_longitude ;;
  }

  dimension: end_station_location {
    type: location
    sql_latitude: ${end_station_latitude} ;;
    sql_longitude: ${end_station_longitude} ;;
  }

  dimension: bike_id {
    type: string
    sql: CAST(${TABLE}.bikeid AS STRING) ;;
  }

  dimension: user_type {
    type: string
    sql: ${TABLE}.usertype ;;
  }

  dimension: is_subscriber {
    type: yesno
    sql: ${user_type} = 'Subscriber' ;;
  }

  dimension: birth_year {
    type: number
    sql: ${TABLE}.birth_year ;;
  }

  dimension: gender {
    type: string
    sql: ${TABLE}.gender ;;
  }

  dimension: customer_plan {
    type: string
    sql: ${TABLE}.customer_plan ;;
  }

  dimension: age {
    type: number
    sql: 2024 - ${birth_year} ;; # simplified
  }

  measure: count {
    type: count
  }

  measure: average_trip_duration {
    type: average
    sql: ${trip_duration} ;;
    value_format_name: decimal_2
  }

  set: trip_rider {
    fields: [customer_plan,gender,birth_year,is_subscriber,user_type,age]
  }

  set: trip_station {
    fields: [end_station_longitude,end_station_latitude.end_station_name,end_station_id,start_station_id,start_station_name,start_station_latitude,start_station_longitude,start_station_location,end_station_location]
  }

  set: trip_details {
    fields: [count,trip_duration,average_trip_duration,start_date,start_week,start_day_of_week,start_day_of_year,start_hour_of_day,start_month,start_week,start_year,stop_time,stop_year,stop_week,stop_month,stop_date]
  }

  set: trips_detail {
    fields: [trip_rider*,trip_details*,trip_station*]
  }
}
