                                # Only update GPS fixes, as soon as it's loaded or comes from the WEB it's untouchable
                                if location.source in [None, "GPS", "KStarsAPI"]:
                                logger.info(
                                    f"Updating GPS location: new content: {gps_content}, old content: {location}"
                                )