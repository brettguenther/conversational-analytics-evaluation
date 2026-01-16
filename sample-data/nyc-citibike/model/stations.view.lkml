view: stations {
  sql_table_name: `@{DATASET_NAME}.citibike_stations` ;;
  drill_fields: [station_id, name]

  dimension: station_id {
    primary_key: yes
    type: string
    sql: ${TABLE}.station_id ;;
  }

  dimension: name {
    type: string
    sql: ${TABLE}.name ;;
  }

  dimension: latitude {
    type: number
    sql: ${TABLE}.latitude ;;
  }

  dimension: longitude {
    type: number
    sql: ${TABLE}.longitude ;;
  }

  dimension: location {
    type: location
    sql_latitude: ${latitude} ;;
    sql_longitude: ${longitude} ;;
  }

  dimension: short_name {
    type: string
    sql: ${TABLE}.short_name ;;
  }

  dimension: region_id {
    type: number
    sql: ${TABLE}.region_id ;;
  }

  dimension: rental_methods {
    type: string
    sql: ${TABLE}.rental_methods ;;
  }

  dimension: capacity {
    type: number
    sql: ${TABLE}.capacity ;;
  }

  dimension: eightd_has_key_dispenser {
    type: yesno
    sql: ${TABLE}.eightd_has_key_dispenser ;;
  }

  measure: station_count {
    type: count
    drill_fields: [station_id, name]
  }

  set: station_details {
    fields: [short_name,eightd_has_key_dispenser,capacity, rental_methods,region_id]
  }

}
