## install docker

[docker for mac](https://store.docker.com/editions/community/docker-ce-desktop-mac)


## install docker-compose

docker-compose is included in docker for mac. on other platforms it may have to be installed separately.

## turn it on
```bash
# foreground
docker-compose up
# background
docker-compose up -d
```

## create db manually

the `openstax/cnx-db` image doesn't come with the cnxarchive db created by default, when you create your container for the
first time you'll have to run these commands to set it up.

TODO - add docker/run-development.sh that ensures db is created and then runs `pserve development.ini`

```bash
docker exec $(docker ps | grep cnx-publishing_cnxdb | awk '{print $1}') psql --user postgres -c 'create database cnxarchive'
docker exec $(docker ps | grep cnx-publishing_cnxpublishing | awk '{print $1}') cnx-db init
```
