connection: "@{CONNECTION_NAME}"

include: "/views/*.view.lkml"

explore: trips {
  fields: [start_station.station_details*, end_station.station_details*,trips.trips_detail*]
  label: "Citi Bike Trips"
  persist_with: daily_etl

  join: start_station {
    from: stations
    type: left_outer
    relationship: many_to_one
    sql_on: ${trips.start_station_id} = ${start_station.station_id} ;;
  }

  join: end_station {
    from: stations
    type: left_outer
    relationship: many_to_one
    sql_on: ${trips.end_station_id} = ${end_station.station_id} ;;
  }
}

explore: stations {}
